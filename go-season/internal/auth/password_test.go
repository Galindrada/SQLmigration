package auth_test

import (
	"testing"

	"github.com/colados/go-season/internal/auth"
)

func TestCheckWerkzeugPassword(t *testing.T) {
	// Generated with Werkzeug pbkdf2:sha256 for "season-demo"
	stored := "pbkdf2:sha256:1000000$OPs5ADZ46vcXxgsu$74947ed45cdd88c3a8f8562546a0f07b8b36b4d90eb412ab37cd08281b7014b4"
	if !auth.CheckWerkzeugPassword(stored, "season-demo") {
		t.Fatal("expected password to verify")
	}
	if auth.CheckWerkzeugPassword(stored, "wrong") {
		t.Fatal("expected wrong password to fail")
	}
}

func TestHashRoundTrip(t *testing.T) {
	h := auth.HashWerkzeugPassword("hello", 100000, "testsalt")
	if !auth.CheckWerkzeugPassword(h, "hello") {
		t.Fatalf("round-trip failed for %s", h)
	}
}
