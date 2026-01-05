# Vught Pace Keeper — Claude Code Prompt Sequence

A Django app for marathon/half-marathon training plan management with Strava integration.

## Project Overview

- **Stack:** Django 5.x, PostGIS, HTMX, Tailwind CSS, django-allauth
- **Auth:** Strava OAuth (primary), email/password (secondary)
- **Units:** min/km for all pace values
- **Deployment:** Digital Ocean App Platform
- **Local Dev:** Docker with testcontainers

---

## Phase 1: Project Foundation & Data Models

```markdown
**MODE: Start in plan mode. Before writing any code, outline:**
1. The directory structure you'll create (src/ layout, app organization)
2. The model relationships diagram (which models reference which)
3. Key field decisions (especially for pace storage, geometry fields)
4. Your docker-compose setup for PostGIS with testcontainers compatibility
5. Any design decisions or trade-offs you're considering

Wait for my approval before implementing.

---

Create a Django 5.x project called "vught_pace_keeper" with the following setup:

**Project Structure:**
- Use a src/ layout with apps: core, accounts, training, strava_integration
- Configure for PostGIS database (django.contrib.gis)
- Set up django-environ for environment variables
- Include a docker-compose.yml with PostGIS container for local dev
- Add pyproject.toml using uv for dependency management
- Set up Tailwind CSS via django-tailwind (or standalone Tailwind CLI)
- Configure tailwind.config.js to scan Django templates

**Core Data Models (training app):**

1. TrainingPlan
   - name, description, plan_type (half_marathon/full_marathon), duration_weeks
   - target_race_date, goal_time (stored as timedelta)
   - user (FK), is_template (boolean for reusable templates)
   - methodology (CharField with choices—start with "custom", extensible for pfitzinger/hanson/80_20 later)

2. TrainingWeek
   - plan (FK), week_number, focus (base/build/peak/taper)
   - total_distance_km, notes

3. ScheduledWorkout
   - week (FK), day_of_week (1-7), workout_type (easy/long/tempo/interval/recovery/rest)
   - target_distance_km, target_duration (timedelta)
   - target_pace_min_per_km (DecimalField), pace_zone (FK, nullable)
   - description, order_in_day

4. CompletedWorkout
   - scheduled_workout (FK, nullable—for unplanned runs)
   - user (FK), date, actual_distance_km, actual_duration
   - average_pace_min_per_km, average_heart_rate, elevation_gain_m
   - route (GeometryField, LineString, nullable), gpx_file (FileField, nullable)
   - source (manual/gpx_upload/strava), strava_activity_id (nullable)
   - perceived_effort (1-10 scale), notes

5. PaceZone
   - user (FK), name (recovery/easy/tempo/threshold/interval/repetition)
   - min_pace_min_per_km, max_pace_min_per_km
   - description, color_hex (for calendar display)

**Requirements:**
- All pace fields use min/km as the base unit
- Add created_at/updated_at timestamps via abstract base model
- Include proper indexes for common queries (user + date lookups)
- Add Django admin configuration for all models

Generate migrations and include sample fixture data for testing.
```

---

## Phase 2: Authentication with Strava OAuth

```markdown
**MODE: Start in plan mode. Before writing code, outline:**
1. How you'll configure django-allauth with the Strava provider
2. The CustomUser model fields and migration strategy (given Phase 1 models exist)
3. Your approach to secure token storage and refresh logic
4. The authentication flow from landing page → Strava → dashboard
5. Any django-allauth settings or adapter customizations needed

Wait for my approval before implementing.

---

Extend vught_pace_keeper with Strava social authentication:

**Setup:**
- Install and configure django-allauth with Strava provider
- Strava OAuth scopes needed: read, activity:read_all, profile:read_all

**accounts app:**

1. CustomUser model extending AbstractUser:
   - Add fields: strava_athlete_id (BigInteger, nullable, unique)
   - preferred_distance_unit (always km, but store for future)
   - date_of_birth (for age-graded calculations)

2. StravaToken model:
   - user (OneToOne), access_token, refresh_token
   - expires_at (datetime), scope
   - Add method: is_expired(), refresh_if_needed()

**Authentication Flow:**
- Landing page with "Connect with Strava" button
- After OAuth, create/update user and store tokens
- Redirect to dashboard after successful auth
- Add manual email/password as secondary option (django-allauth handles both)

**Templates (Django templates + HTMX + Tailwind):**
- Base template with navigation (show user's Strava profile pic if available)
- Login page with Strava button prominently featured
- Simple dashboard placeholder showing "Welcome, {first_name}"
- Use Tailwind utility classes for all styling
- Establish reusable component patterns (buttons, cards, form inputs)

**Security:**
- Store tokens encrypted at rest (django-cryptography or similar)
- Add token refresh middleware/utility
- Environment variables for STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET

Include the Strava brand guidelines compliant button (orange "Connect with Strava").
```

---

## Phase 3: Plan Template Engine (Extensible Architecture)

```markdown
**MODE: Start in plan mode. Before writing code, outline:**
1. The abstract base class design and method signatures
2. How the registry pattern will work for auto-discovering generators
3. The validation rules and where they'll be enforced
4. The multi-step wizard flow and HTMX interactions

Wait for my approval before implementing.

---

Build the training plan template engine with extensibility in mind:

**Architecture (training app):**

1. Create an abstract PlanGenerator base class:
   ```python
   class BasePlanGenerator(ABC):
       methodology_name: str
       supported_distances: list[str]  # ["half_marathon", "full_marathon"]
       
       @abstractmethod
       def generate_plan(self, user, race_date, goal_time, current_fitness) -> TrainingPlan:
           pass
       
       @abstractmethod
       def get_week_focus(self, week_number, total_weeks) -> str:
           pass
   ```

2. Implement CustomPlanGenerator as first concrete class:
   - Allow users to define their own week-by-week structure
   - Support copying/modifying existing templates
   - Validate total distance progression (no crazy jumps)

3. Create PlanGeneratorRegistry:
   - Auto-discovers generators via entry points or app registry
   - Returns available methodologies for dropdown selection
   - Example: registry.get_generator("custom").generate_plan(...)

**Views & Templates:**
- "Create New Plan" wizard (multi-step form with HTMX):
  1. Select distance (half/full) and methodology
  2. Set race date and goal time
  3. Preview generated plan structure
  4. Confirm and create
  
- Plan detail view showing all weeks/workouts in expandable accordion
- Edit capability for custom plans (drag-drop workout reordering would be nice but not required for v1)

**Validation:**
- Goal time sanity checks based on distance
- Race date must be in future
- Minimum weeks based on methodology (e.g., 12 weeks minimum for custom marathon plan)

Make it easy to add a new generator by just creating a new class file—no core code changes needed.
```

---

## Phase 4: Manual Logging & GPX Upload

```markdown
Add manual workout logging and GPX file parsing:

**GPX Processing (training app or new gpx_parser app):**

1. GPX Parser utility:
   - Parse GPX files using gpxpy library
   - Extract: total distance, duration, elevation gain/loss
   - Calculate average pace (min/km)
   - Convert track to PostGIS LineString geometry
   - Handle edge cases: paused activities, missing timestamps

2. GPX Upload endpoint:
   - Accept .gpx file upload (max 10MB)
   - Process async if file is large (consider django-q2 or simple background task)
   - Show processing status with HTMX polling
   - Preview extracted data before saving

**Manual Logging Form:**
- Quick-add form for runs without GPS:
  - Date, distance (km), duration (HH:MM:SS input)
  - Auto-calculate pace on input (HTMX)
  - Workout type dropdown
  - Optional: perceived effort, heart rate (manual entry), notes

**Workout Completion Flow:**
- From calendar/plan view, click scheduled workout → "Log Completion"
- Choose: Manual entry / Upload GPX / (later: Pull from Strava)
- Pre-fill target values from scheduled workout
- Show comparison: planned vs actual (pace, distance)

**Views & Templates:**
- Workout log history with filtering (date range, workout type)
- Individual workout detail page showing:
  - Stats summary
  - Map with route if geometry exists (use Leaflet.js)
  - Elevation profile if data available
  - Link to Strava activity if synced

Keep Leaflet integration simple—just embed via CDN, no build step needed.
```

---

## Phase 5: Pace Zone Calculator

```markdown
Implement pace zone calculator based on race results or threshold tests:

**Pace Zone Logic (training app):**

1. Zone calculation methods:
   - From recent race: Input race distance + time → calculate VDOT or similar
   - From threshold test: Input threshold pace directly
   - Support Jack Daniels' VDOT formula as primary method

2. Standard zones to generate (all in min/km):
   - Recovery: ~60-65% effort
   - Easy: 65-75% effort  
   - Tempo/Marathon pace: 80-85% effort
   - Threshold: 85-90% effort
   - Interval (VO2max): 95-100% effort
   - Repetition: faster than VO2max pace

3. PaceZoneCalculator service:
   ```python
   class PaceZoneCalculator:
       def from_race_result(self, distance_km: float, time: timedelta) -> list[PaceZone]:
           # Calculate VDOT, derive training paces
           pass
       
       def from_threshold_pace(self, threshold_pace_min_per_km: Decimal) -> list[PaceZone]:
           pass
   ```

**Views & Templates:**
- "Calculate My Zones" page:
  - Tab 1: Enter recent race (dropdown: 5K/10K/half/full + time)
  - Tab 2: Enter threshold pace directly
  - Show results instantly with HTMX
  - Display as colored pace range cards
  
- "My Pace Zones" management:
  - View current zones
  - Recalculate button
  - Manual override capability (some runners know their zones)
  - Show zone history (track fitness progression over time)

**Integration:**
- When creating workouts, suggest appropriate zone based on workout type
- In workout completion, show which zone the actual pace fell into
- Color-code calendar entries by primary zone of workout

Format all pace displays as M:SS/km (e.g., "5:30/km" not "5.5 min/km").
```

---

## Phase 6: Strava Activity Sync

```markdown
**MODE: Start in plan mode. Before writing code, outline:**
1. The StravaClient class design and error handling strategy
2. Token refresh flow and where it hooks in
3. Activity mapping logic (Strava fields → CompletedWorkout fields)
4. The matching algorithm for linking activities to scheduled workouts
5. Rate limit handling approach

Wait for my approval before implementing.

---

Implement Strava activity synchronization:

**Strava API Client (strava_integration app):**

1. StravaClient service class:
   - Initialize with user's tokens (auto-refresh if expired)
   - Methods:
     - get_athlete_profile()
     - get_activities(after: datetime, before: datetime) -> list
     - get_activity_detail(activity_id) -> dict (includes streams)
     - get_activity_streams(activity_id, types=['latlng', 'altitude', 'heartrate', 'time'])

2. Activity sync logic:
   - Fetch activities since last sync (store last_sync_timestamp per user)
   - Filter to type="Run" only
   - Map Strava activity to CompletedWorkout:
     - Convert distance meters → km
     - Calculate pace from distance/time
     - Convert polyline to PostGIS LineString
     - Store strava_activity_id for deduplication

3. Matching to scheduled workouts:
   - Auto-match by date if scheduled workout exists
   - If multiple scheduled on same day, prompt user to select
   - Allow manual matching/unlinking

**Views & Templates:**
- "Sync with Strava" button on dashboard (HTMX with loading spinner)
- Sync status: "Last synced: X hours ago, Y activities imported"
- Activity import review:
  - Show newly imported activities
  - Suggest matches to scheduled workouts
  - Bulk confirm or individual review

**Settings:**
- Auto-sync toggle (for webhook phase)
- Sync historical activities: date range picker for initial backfill
- Option to re-sync specific activity (if data was updated on Strava)

Handle Strava API rate limits gracefully (100 requests per 15 min, 1000 per day).
```

---

## Phase 7: Strava Webhooks

```markdown
**MODE: Start in plan mode. Before writing code, outline:**
1. Webhook endpoint design and URL structure
2. Signature verification approach
3. Event processing flow (sync vs async)
4. django-q2 task structure for background processing
5. Local development testing strategy (ngrok setup)

Wait for my approval before implementing.

---

Add Strava webhook subscription for real-time activity sync:

**Webhook Setup (strava_integration app):**

1. Webhook endpoint:
   - GET /strava/webhook/ — handle Strava's validation challenge
   - POST /strava/webhook/ — receive activity events
   
2. Event handling:
   - Event types to handle: activity.create, activity.update, activity.delete
   - On create: queue activity fetch and sync
   - On update: re-fetch and update CompletedWorkout
   - On delete: mark CompletedWorkout.strava_activity_id as null, keep workout

3. Subscription management:
   - Management command: python manage.py strava_subscribe
   - Store subscription_id in database or settings
   - View subscription status in admin

**Background Processing:**
- Use django-q2 for async webhook processing
- Queue structure:
  ```python
  @async_task
  def process_strava_webhook(event_type: str, activity_id: int, athlete_id: int):
      # Fetch activity details and sync
      pass
  ```

**Security:**
- Verify webhook signature using subscription's verify_token
- Rate limit webhook endpoint
- Log all webhook events for debugging

**Development/Testing:**
- Document ngrok setup for local webhook testing
- Add mock webhook sender management command for testing
- Include webhook event fixtures

**Views:**
- Admin view showing recent webhook events and processing status
- User setting to enable/disable webhook sync (some may prefer manual)
```

---

## Phase 8: Calendar View with HTMX

```markdown
**MODE: Start in plan mode. Before writing code, outline:**
1. Calendar data structure and query optimization strategy
2. HTMX interaction patterns (which endpoints, what triggers)
3. CSS approach for the grid layout (responsive breakpoints)
4. iCal generation approach

Wait for my approval before implementing.

---

Build an interactive calendar view for training plans:

**Calendar Implementation (training app):**

1. Calendar component:
   - Monthly view as primary (week view as secondary option)
   - Show scheduled workouts with color-coding by workout type or pace zone
   - Overlay completed workouts (checkmark or fill indicator)
   - Visual distinction: planned only / completed / missed

2. HTMX interactions:
   - Navigate months without full page reload
   - Click day → expand to show workout details inline
   - Click workout → slide-out panel with full details
   - Quick-add workout button per day
   - Drag-drop to reschedule (stretch goal, use SortableJS if implemented)

3. Calendar data structure:
   ```python
   def get_calendar_data(user, year, month):
       # Return dict with:
       # - days: list of {date, scheduled: [], completed: [], is_rest_day}
       # - stats: {total_planned_km, total_completed_km, completion_rate}
       pass
   ```

**Templates:**
- Calendar grid using CSS Grid via Tailwind (responsive: grid-cols-7 on desktop, stacked list on mobile)
- Color legend showing workout types
- Month stats summary bar (planned km, completed km, % completion)
- Export button: iCal format for external calendar apps

**iCal Export:**
- Generate .ics file with scheduled workouts as events
- Include workout details in event description
- Proper timezone handling (Europe/Amsterdam default for you)
- Subscribe URL for live calendar updates

**Mobile Considerations:**
- Swipe navigation between months (optional enhancement)
- Day view as default on small screens
- Large touch targets for workout interaction

Use Tailwind CSS for all styling with responsive utilities (sm:, md:, lg:). Consider extracting repeated patterns into @apply-based component classes in your CSS.
```

---

## Phase 9: Adaptive Plan Logic (Feature-Flagged)

```markdown
**MODE: Start in plan mode. Before writing code, outline:**
1. The adaptation rules you'll implement (be specific)
2. Data requirements: what metrics need N weeks of data
3. The suggestion → approval → apply flow
4. Safeguard boundaries and how they're enforced
5. Feature flag integration points

Wait for my approval before implementing.

---

Implement adaptive training plan adjustments based on completed workouts:

**Feature Flag Setup:**
- Add django-flags or simple boolean setting per user
- Flag: "adaptive_plans_enabled" (default: False)
- Show as beta feature in user settings

**Adaptation Logic (training app):**

1. Workout analysis after completion:
   - Compare actual vs target pace
   - Track completion rate (did they do the full distance?)
   - Monitor perceived effort vs actual effort
   - Detect patterns: consistently too fast/slow, skipping long runs, etc.

2. Adaptation rules engine:
   ```python
   class PlanAdapter:
       def analyze_recent_performance(self, user, weeks_back=2) -> PerformanceAnalysis:
           # Return: completion_rate, avg_pace_deviation, effort_trend
           pass
       
       def suggest_adjustments(self, plan, analysis) -> list[Adjustment]:
           # Return list of suggested changes
           pass
       
       def apply_adjustments(self, plan, adjustments, auto=False):
           # Apply if auto, otherwise queue for user approval
           pass
   ```

3. Adjustment types:
   - Pace zone recalculation (fitness improved/declined)
   - Volume adjustment (increase if handling well, decrease if struggling)
   - Extra recovery day insertion
   - Workout swap (e.g., tempo → easy if fatigued)

**User Experience:**
- Weekly summary notification (email optional) with adaptation suggestions
- "Review Suggestions" page:
  - Show each suggestion with reasoning
  - Accept/reject individually or in bulk
  - "Trust the system" toggle for auto-apply
  
- Visual indicator on calendar when a workout was auto-adjusted
- Audit log of all plan changes (manual and adaptive)

**Safeguards:**
- Never increase weekly volume more than 10%
- Always preserve taper period structure
- Require minimum data (2 weeks of workouts) before adapting
- Human override always available

This should feel like a helpful coach, not an annoying nanny.
```

---

## Phase 10: Digital Ocean Deployment

```markdown
**MODE: Start in plan mode. Before writing code, outline:**
1. The app.yaml structure for DO App Platform
2. Dockerfile stages and GDAL/PostGIS dependencies
3. Settings file organization (base/dev/prod split)
4. CI/CD pipeline stages and test strategy
5. Any infrastructure-as-code approach (Terraform/Pulumi)

Wait for my approval before implementing.

---

Prepare vught_pace_keeper for Digital Ocean deployment:

**Infrastructure Setup:**

1. Digital Ocean App Platform configuration:
   - Create app.yaml / .do/app.yaml spec file
   - Components:
     - Web service: Django with gunicorn
     - Worker service: django-q2 for background tasks
     - Database: Digital Ocean Managed PostgreSQL with PostGIS
     - Redis: For django-q2 broker and cache (optional: DO managed Redis)

2. Docker configuration:
   - Production Dockerfile (multi-stage build):
     - Build stage: install dependencies with uv
     - Runtime stage: slim Python image with GDAL/PostGIS libs
   - docker-compose.prod.yml for local production simulation

3. Environment configuration:
   - Separate settings: base.py, development.py, production.py
   - Required env vars:
     - DATABASE_URL, REDIS_URL
     - SECRET_KEY, DEBUG=False
     - STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET
     - ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS
   - Document all env vars in .env.example

**Production Hardening:**
- django-csp for Content Security Policy
- Secure cookie settings
- HSTS headers
- Proper CORS configuration for API endpoints if any
- Sentry integration for error tracking (optional)

**Static Files & Media:**
- WhiteNoise for static files
- Digital Ocean Spaces for media (GPX files, profile images)
- Configure django-storages for Spaces

**CI/CD:**
- GitHub Actions workflow:
  - Run tests with testcontainers (PostgreSQL + PostGIS)
  - Lint with ruff
  - Build Tailwind CSS for production
  - Build Docker image
  - Deploy to DO App Platform on main branch push

**Database Migrations:**
- Release phase command for migrations
- Backup strategy documentation

**Monitoring:**
- Health check endpoint (/health/)
- Structured logging (JSON format)
- Basic metrics: response time, error rate

**Documentation:**
- README with:
  - Local development setup (docker-compose up)
  - Running tests
  - Deployment steps
  - Environment variables reference
- CONTRIBUTING.md with code style guidelines

Include Terraform or Pulumi config as bonus for infrastructure-as-code (given your platform engineering background).
```

---

## Quick Reference: Plan Mode by Phase

| Phase | Plan Mode | Reason |
|-------|-----------|--------|
| 1. Foundation & Models | ✅ Yes | Core architecture decisions, model relationships |
| 2. Strava OAuth | ✅ Yes | Auth flows, token handling, migration strategy |
| 3. Plan Engine | ✅ Yes | Abstract design, registry pattern |
| 4. Manual Logging & GPX | ❌ No | Straightforward implementation |
| 5. Pace Zones | ❌ No | Self-contained, well-defined |
| 6. Strava Sync | ✅ Yes | API integration, rate limits, matching logic |
| 7. Webhooks | ✅ Yes | Async processing, security, local dev setup |
| 8. Calendar | ✅ Yes | HTMX patterns, query optimization |
| 9. Adaptive Logic | ✅ Yes | Rules engine, safeguards, complex UX |
| 10. Deployment | ✅ Yes | Infrastructure decisions, CI/CD |

---

## Session Tips for Claude Code

**Starting a session:**
> "Continuing vught_pace_keeper. Phases 1-3 complete. Starting Phase 4: GPX upload and manual logging."

**Scope control:**
> "Let's keep this minimal for now. We can enhance in a future iteration."

**Demo milestones:**
- After Phase 3: Core planning functionality works
- After Phase 6: Strava integration functional
- After Phase 8: Full user experience with calendar