# Vught Pace Keeper - Development Context

## Project Overview
Marathon training plan management system with Strava integration, built with Django 5.x and PostGIS.

## Tech Stack
- **Backend**: Django 5.1+ with GeoDjango
- **Database**: PostgreSQL 16 with PostGIS 3.4
- **Authentication**: django-allauth with Strava OAuth
- **Frontend**: Django templates + HTMX
- **Package Manager**: uv
- **Containerization**: Docker Compose

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

## Commands

### Development
```bash
# Start all services
docker-compose up -d

# Run Django commands
docker-compose run --rm web uv run python manage.py <command>

# Make migrations
docker-compose run --rm web uv run python manage.py makemigrations

# Apply migrations
docker-compose run --rm web uv run python manage.py migrate

# Create superuser
docker-compose run --rm web uv run python manage.py createsuperuser

# Load sample data
docker-compose run --rm web uv run python manage.py loaddata sample_data

# View logs
docker-compose logs -f web
```

### Database
```bash
# Access PostgreSQL
docker-compose exec db psql -U vught_user -d vught_pace_keeper
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
# Django SECRET_KEY
docker-compose run --rm web uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# FERNET_KEY (for token encryption)
docker-compose run --rm web uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## URLs
- `/` - Landing page
- `/dashboard/` - User dashboard (requires login)
- `/admin/` - Django admin
- `/accounts/login/` - Email login
- `/accounts/strava/login/` - Strava OAuth login
- `/accounts/logout/` - Logout

## Current State (Dec 2025)

### Completed
- [x] Project scaffolding with Docker + PostGIS
- [x] Custom User model with Strava fields
- [x] Training models (plans, weeks, workouts, pace zones)
- [x] django-allauth with Strava provider
- [x] Strava OAuth login flow working
- [x] Encrypted token storage (Fernet with SALT_KEY)
- [x] Token refresh utility
- [x] HTMX-ready templates (base, landing, dashboard)
- [x] Sample fixture data for training plans
- [x] Django admin configuration

### Next Steps
- [ ] Strava activity sync (fetch activities from API)
- [ ] Match completed workouts to scheduled workouts
- [ ] Pace zone analysis for completed workouts
- [ ] Training plan progress visualization
- [ ] HTMX partial updates for dashboard
- [ ] Webhook receiver for real-time Strava updates
- [ ] Age-graded performance calculations

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
# Run tests
docker-compose run --rm web uv run pytest

# Run with coverage
docker-compose run --rm web uv run pytest --cov=vught_pace_keeper
```

## Fixtures
Sample data in `training/fixtures/sample_data.json`:
- 5 pace zones (recovery, easy, tempo, threshold, interval)
- 1 training plan (12-Week Half Marathon)
- 2 training weeks
- 7 scheduled workouts for week 1
