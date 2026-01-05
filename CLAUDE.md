# Vught Pace Keeper - Development Context

## Project Overview
Marathon training plan management system with Strava integration, built with Django 5.x and PostGIS.

## Tech Stack
- **Backend**: Django 5.1+ with GeoDjango
- **Database**: PostgreSQL 16 with PostGIS 3.4
- **Authentication**: django-allauth with Strava OAuth
- **Frontend**: Django templates + HTMX
- **Package Manager**: uv
- **Task Runner**: just (justfile)
- **Dev Environment**: WSL2 + Docker (DB only)

## Project Structure
```
vught-pace-keeper/
├── src/vught_pace_keeper/
│   ├── core/              # Base models (TimestampedModel)
│   ├── accounts/          # User model, Strava tokens, auth adapters
│   ├── training/          # Training plans, workouts, pace zones
│   ├── strava_integration/# Strava API utilities (placeholder)
│   └── templates/         # Django templates with HTMX
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── .env
```

## Key Models

### accounts app
- `User` (AbstractUser) - Custom user with Strava fields
  - `strava_athlete_id`: BigIntegerField (unique)
  - `strava_profile_picture_url`: URLField
  - `preferred_distance_unit`: km/mi choice
  - `date_of_birth`: DateField (for age-graded calculations)
- `StravaToken` - Encrypted OAuth tokens
  - `access_token`: EncryptedTextField
  - `refresh_token`: EncryptedTextField
  - `expires_at`: DateTimeField
  - `scope`: CharField

### training app
- `PaceZone` - User-defined pace zones (recovery, easy, tempo, threshold, interval)
- `TrainingPlan` - Marathon/half-marathon training plans
- `TrainingWeek` - Weekly structure within a plan
- `ScheduledWorkout` - Planned workouts with target pace/distance
- `CompletedWorkout` - Actual completed workouts with GPS route (LineStringField)

## Authentication Flow
1. Landing page (`/`) shows "Connect with Strava" button
2. Strava OAuth via `/accounts/strava/login/`
3. Callback stores athlete data on User model
4. Tokens stored encrypted in StravaToken model
5. Redirect to `/dashboard/`

## Development Environment

**WSL2 Setup**: Django runs directly in WSL2 via uv, while PostgreSQL/PostGIS runs in Docker.

```bash
# One-time WSL setup (install GDAL/GEOS for GeoDjango)
just setup-wsl

# Install Python dependencies
just install
```

**Important**: DATABASE_URL in `.env` must use `localhost` (not `db`) since Django runs in WSL:
```
DATABASE_URL=postgis://vught_user:vught_pass@localhost:5432/vught_pace_keeper
```

## Commands

All commands use `just` (see `justfile` for full list):

```bash
# Start database container
just db

# Run development server
just run

# Fresh start (db + migrate + fixtures + run)
just fresh

# Quick start (db + run, assumes migrations applied)
just start
```

### Django Commands
```bash
just makemigrations          # Make migrations
just migrate                 # Apply migrations
just superuser               # Create superuser
just fixtures                # Load sample data
just shell                   # Django shell
just test                    # Run tests
just test-cov                # Tests with coverage
```

### Utilities
```bash
just lint                    # Run ruff linter
just lint-fix                # Auto-fix lint issues
just fmt                     # Format code with ruff
just secret-key              # Generate Django secret key
just fernet-key              # Generate Fernet encryption key
```

### Database
```bash
just db-shell                # PostgreSQL shell
just db-stop                 # Stop database
just db-reset                # Reset database (destructive!)
```

## Environment Variables
Required in `.env`:
- `SECRET_KEY` - Django secret key (50 random characters)
- `DEBUG` - True for development
- `DATABASE_URL` - PostGIS connection string
- `STRAVA_CLIENT_ID` - From https://www.strava.com/settings/api
- `STRAVA_CLIENT_SECRET` - From Strava API settings
- `FERNET_KEY` - Encryption key for tokens (optional, defaults to SECRET_KEY)
- `SALT_KEY` - Salt for encryption (optional, defaults to first 16 chars of SECRET_KEY)

### Generate Keys
```bash
just secret-key    # Django SECRET_KEY
just fernet-key    # FERNET_KEY for token encryption
```

## URLs
- `/` - Landing page
- `/dashboard/` - User dashboard (requires login)
- `/admin/` - Django admin
- `/accounts/login/` - Email login
- `/accounts/strava/login/` - Strava OAuth login
- `/accounts/logout/` - Logout
- `/training/plans/` - Training plan list
- `/training/workouts/` - Workout log
- `/training/zones/` - Pace zones management
- `/training/zones/calculator/` - Pace zone calculator (VDOT-based)

## Current State (Jan 2026)

### Completed Phases
- [x] **Phase 1**: Project scaffolding with Docker + PostGIS
- [x] **Phase 2**: Strava OAuth with django-allauth, encrypted token storage
- [x] **Phase 3**: Training plan template engine (custom plans, multi-step wizard)
- [x] **Phase 4**: Manual workout logging, GPX upload with route display
- [x] **Phase 5**: Pace zone calculator (VDOT-based, race result or threshold input)

### Next Phase: 6 - Strava Activity Sync
- [ ] StravaClient service class with auto token refresh
- [ ] Fetch and sync activities from Strava API
- [ ] Match synced activities to scheduled workouts
- [ ] Activity import review UI

## API Integration Notes

### Strava Scopes
Configured in `settings.py` as comma-separated string in list format:
```python
"SCOPE": ["read,activity:read_all"]
```

Valid scopes:
- `read` - Public segments, routes, profile data, posts, events
- `read_all` - Private routes, segments, and events
- `activity:read` - Public activities only
- `activity:read_all` - All activities including private
- `activity:write` - Create/edit activities
- `profile:read_all` - Full profile even if private
- `profile:write` - Update weight/FTP

### Token Refresh
Tokens are automatically refreshed via `StravaToken.refresh_if_needed()` method.
Uses `accounts/strava_utils.py:refresh_strava_token()`.

## Testing
```bash
just test          # Run tests
just test-cov      # Run with coverage
```

## Fixtures
Sample data in `training/fixtures/sample_data.json`:
- 5 pace zones (recovery, easy, tempo, threshold, interval)
- 1 training plan (12-Week Half Marathon)
- 2 training weeks
- 7 scheduled workouts for week 1
