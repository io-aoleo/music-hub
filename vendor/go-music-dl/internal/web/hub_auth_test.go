package web

import (
 "net/http/httptest"
 "strings"
 "testing"
 "github.com/gin-gonic/gin"
)

func TestHubInternalToken(t *testing.T) {
 token := strings.Repeat("a", 43)
 t.Setenv("ENGINE_INTERNAL_TOKEN",token)
 ctx,_:=gin.CreateTestContext(httptest.NewRecorder())
 ctx.Request=httptest.NewRequest("POST","/music/download",nil)
 if hubAuthorized(ctx) {t.Fatal("missing token accepted")}
 ctx.Request.Header.Set("X-Music-Hub-Token","invalid")
 if hubAuthorized(ctx) {t.Fatal("wrong token accepted")}
 ctx.Request.Header.Set("X-Music-Hub-Token",token)
 if !hubAuthorized(ctx) {t.Fatal("valid token rejected")}
 ctx.Request.Header.Set("X-Requested-With","XMLHttpRequest")
 if !allowAuthenticatedSaveLocal(ctx) {t.Fatal("internal scheduler rejected")}
 t.Setenv("ENGINE_INTERNAL_TOKEN","")
 ctx.Request.Header.Set("X-Music-Hub-Token","")
 if hubAuthorized(ctx) {t.Fatal("empty configured token accepted")}
}
