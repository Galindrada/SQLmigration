package auth

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strconv"
	"strings"

	"golang.org/x/crypto/pbkdf2"
)

// CheckWerkzeugPassword verifies Flask/Werkzeug pbkdf2:sha256 hashes
// stored in the shared users.password column.
func CheckWerkzeugPassword(stored, password string) bool {
	stored = strings.TrimSpace(stored)
	if stored == "" || password == "" {
		return false
	}

	// pbkdf2:sha256:iterations$salt$hexdigest
	parts := strings.SplitN(stored, "$", 3)
	if len(parts) != 3 {
		return false
	}
	methodParts := strings.Split(parts[0], ":")
	if len(methodParts) != 3 || methodParts[0] != "pbkdf2" || methodParts[1] != "sha256" {
		return false
	}
	iterations, err := strconv.Atoi(methodParts[2])
	if err != nil || iterations <= 0 {
		return false
	}
	salt := []byte(parts[1])
	want, err := hex.DecodeString(parts[2])
	if err != nil {
		return false
	}
	got := pbkdf2.Key([]byte(password), salt, iterations, len(want), sha256.New)
	if len(got) != len(want) {
		return false
	}
	// constant-time compare
	var diff byte
	for i := range got {
		diff |= got[i] ^ want[i]
	}
	return diff == 0
}

func HashWerkzeugPassword(password string, iterations int, salt string) string {
	if iterations <= 0 {
		iterations = 600000
	}
	dk := pbkdf2.Key([]byte(password), []byte(salt), iterations, 32, sha256.New)
	return fmt.Sprintf("pbkdf2:sha256:%d$%s$%s", iterations, salt, hex.EncodeToString(dk))
}
