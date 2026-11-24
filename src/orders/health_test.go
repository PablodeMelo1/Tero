package main

import (
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"testing"
)

func TestContainerHealthProbe(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/health" {
			w.WriteHeader(http.StatusServiceUnavailable)
		}
	}))
	defer server.Close()
	if !checkHealth(server.URL + "/health") {
		t.Fatal("healthy service rejected")
	}
	if checkHealth(server.URL + "/unhealthy") {
		t.Fatal("unhealthy service accepted")
	}
	if checkHealth("://invalid") {
		t.Fatal("failed connection accepted")
	}
	parsed, err := url.Parse(server.URL)
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("PORT", parsed.Port())
	original := os.Args
	t.Cleanup(func() { os.Args = original })
	os.Args = []string{"service", "--healthcheck"}
	main() // Must return without attempting database initialization.
}
