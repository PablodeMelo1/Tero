package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestBuildDSN(t *testing.T) {
	t.Setenv("RETAIL_ORDERS_PERSISTENCE_ENDPOINT", "database:5434")
	t.Setenv("RETAIL_ORDERS_PERSISTENCE_USERNAME", "ci_user")
	t.Setenv("RETAIL_ORDERS_PERSISTENCE_PASSWORD", "")
	t.Setenv("RETAIL_ORDERS_PERSISTENCE_NAME", "ci_orders")
	if got := buildDSN(); got != "host=database port=5434 user=ci_user password= dbname=ci_orders sslmode=disable" {
		t.Fatalf("unexpected DSN: %s", got)
	}
	t.Setenv("RETAIL_ORDERS_PERSISTENCE_ENDPOINT", "database")
	if !strings.Contains(buildDSN(), "port=5432") {
		t.Fatal("missing default port")
	}
}

func TestGetEnv(t *testing.T) {
	t.Setenv("TERO_TEST_VALUE", "")
	if getEnv("TERO_TEST_VALUE", "fallback") != "fallback" {
		t.Fatal("missing fallback")
	}
	t.Setenv("TERO_TEST_VALUE", "configured")
	if getEnv("TERO_TEST_VALUE", "fallback") != "configured" {
		t.Fatal("ignored configured value")
	}
}

func TestCreateOrderRejectsMalformedJSON(t *testing.T) {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.POST("/orders", createOrder)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, httptest.NewRequest(http.MethodPost, "/orders", strings.NewReader("{")))
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("status = %d", recorder.Code)
	}
}
