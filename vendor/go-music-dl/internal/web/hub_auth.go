// Music Hub integration, 2026-10-21. Original code remains under AGPL-3.0.
package web

import (
 "crypto/subtle"
 "os"
 "github.com/gin-gonic/gin"
)

// Internal token is supplied only by the gateway or scheduler, never embedded in browser scripts.
func hubAuthorized(c *gin.Context) bool {
 expected := os.Getenv("ENGINE_INTERNAL_TOKEN")
 provided := c.GetHeader("X-Music-Hub-Token")
 return len(expected) >= 32 && subtle.ConstantTimeCompare([]byte(expected), []byte(provided)) == 1
}
