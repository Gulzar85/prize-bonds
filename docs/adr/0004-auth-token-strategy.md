# ADR-0004: Authentication Token Strategy

## Status
Accepted

## Context
We need authentication for web (session), mobile (JWT), and desktop (JWT) clients. django-allauth headless is used for the auth flows.

## Decision
- Use django-allauth in headless mode for signup, login, MFA, password reset
- Use djangorestframework-simplejwt for JWT tokens (access/refresh)
- Check if allauth headless provides built-in JWT strategy; if not, implement custom TokenStrategy
- Access tokens: 15 minutes, refresh tokens: 30 days with rotation and blacklisting
- Session auth only for Django admin
- Admin requires MFA for staff users

## Consequences
- Unified auth flows through allauth
- JWT suitable for mobile/desktop
- Token rotation improves security
- Need to handle token strategy compatibility
- More complex auth setup but flexible
