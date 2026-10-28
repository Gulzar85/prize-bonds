# ADR-0002: Custom User Model and UUIDv7 Primary Keys

## Status
Accepted

## Context
We need a flexible user model from the start (email auth, no username) and globally unique, time-ordered IDs for distributed systems.

## Decision
- Create custom User model with email as USERNAME_FIELD before first migration
- Use UUIDv7 (from Python 3.14 stdlib) as primary keys for all models
- No username field, optional phone in E.164 format

## Consequences
- Can't easily switch to default User model later
- UUIDs are larger than integers but provide better security and distribution
- UUIDv7 provides time-ordering benefits
- Better for API exposure (no sequential ID enumeration)
