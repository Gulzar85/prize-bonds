# ADR-0001: Monorepo Structure

## Status
Accepted

## Context
We need to support multiple clients (web, Android, desktop) consuming a single Django API. Code sharing, version consistency, and coordinated releases are important.

## Decision
Use a monorepo structure with separate directories for each client and shared packages.

## Consequences
- Easier to keep API contracts in sync
- Can share types/schemas across clients
- Single CI/CD pipeline possible
- Larger repo but better for coordinated development
- Need clear ownership boundaries
