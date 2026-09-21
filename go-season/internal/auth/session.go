package auth

import (
	"crypto/rand"
	"encoding/hex"
	"net/http"
	"sync"
	"time"
)

const CookieName = "go_season_session"

type User struct {
	ID       int64
	Username string
	Email    string
	IsAdmin  bool
}

type session struct {
	User      User
	ExpiresAt time.Time
}

type Store struct {
	mu      sync.RWMutex
	byToken map[string]session
	ttl     time.Duration
	secure  bool
}

func NewStore(secure bool) *Store {
	return &Store{
		byToken: make(map[string]session),
		ttl:     7 * 24 * time.Hour,
		secure:  secure,
	}
}

func (s *Store) Create(w http.ResponseWriter, user User) error {
	token, err := randomToken(32)
	if err != nil {
		return err
	}
	s.mu.Lock()
	s.byToken[token] = session{User: user, ExpiresAt: time.Now().Add(s.ttl)}
	s.mu.Unlock()

	http.SetCookie(w, &http.Cookie{
		Name:     CookieName,
		Value:    token,
		Path:     "/",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		Secure:   s.secure,
		MaxAge:   int(s.ttl.Seconds()),
	})
	return nil
}

func (s *Store) Clear(w http.ResponseWriter, r *http.Request) {
	if c, err := r.Cookie(CookieName); err == nil {
		s.mu.Lock()
		delete(s.byToken, c.Value)
		s.mu.Unlock()
	}
	http.SetCookie(w, &http.Cookie{
		Name:     CookieName,
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		MaxAge:   -1,
	})
}

func (s *Store) UserFromRequest(r *http.Request) (User, bool) {
	c, err := r.Cookie(CookieName)
	if err != nil || c.Value == "" {
		return User{}, false
	}
	s.mu.RLock()
	sess, ok := s.byToken[c.Value]
	s.mu.RUnlock()
	if !ok || time.Now().After(sess.ExpiresAt) {
		if ok {
			s.mu.Lock()
			delete(s.byToken, c.Value)
			s.mu.Unlock()
		}
		return User{}, false
	}
	return sess.User, true
}

func randomToken(n int) (string, error) {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return hex.EncodeToString(b), nil
}
