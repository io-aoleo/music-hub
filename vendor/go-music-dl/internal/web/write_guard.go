package web

import (
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/guohuiyuan/go-music-dl/core"
)

// skipSaveLocalAuth is true for desktop mode (DisableAuth), where local saves
// should not require a web admin session.
var skipSaveLocalAuth bool

func wantsSaveLocal(c *gin.Context) bool {
	return c != nil && strings.TrimSpace(c.Query("save_local")) == "1"
}

func allowSameOriginWrite(c *gin.Context) bool {
	if c == nil {
		return false
	}
	if c.GetHeader("X-Requested-With") != "XMLHttpRequest" {
		return false
	}

	origin := strings.TrimSpace(c.GetHeader("Origin"))
	if origin != "" {
		parsed, err := url.Parse(origin)
		if err != nil {
			return false
		}
		return strings.EqualFold(parsed.Host, c.Request.Host)
	}

	secFetchSite := strings.TrimSpace(strings.ToLower(c.GetHeader("Sec-Fetch-Site")))
	return secFetchSite == "" || secFetchSite == "same-origin" || secFetchSite == "same-site" || secFetchSite == "none"
}

func allowAuthenticatedSaveLocal(c *gin.Context) bool {
	if skipSaveLocalAuth || hubAuthorized(c) {
		return true
	}
	settings, err := core.GetWebAuthSettings()
	if err != nil {
		c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": "读取登录配置失败"})
		return false
	}
	if !authConfigured(settings) {
		c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
			"error":         "请先初始化并登录管理员账号后再保存到服务器",
			"setupRequired": true,
		})
		return false
	}
	value, err := c.Cookie(authCookieName)
	if err != nil || !validateSessionValue(settings, value, time.Now()) {
		c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
			"error": "未登录用户只能使用浏览器下载，请先登录后再保存到服务器",
		})
		return false
	}
	c.Set("AuthUsername", settings.Username)
	return true
}

func allowSaveLocalRequest(c *gin.Context) bool {
	if !wantsSaveLocal(c) {
		return false
	}
	if c.Request.Method != http.MethodPost {
		c.AbortWithStatusJSON(http.StatusMethodNotAllowed, gin.H{"error": "save_local requires POST"})
		return false
	}
	if !allowSameOriginWrite(c) {
		c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "forbidden"})
		return false
	}
	if !allowAuthenticatedSaveLocal(c) {
		return false
	}
	return true
}
