# Backend Caching

## Overview

The rankings API endpoint uses Django's built-in view caching for optimal performance.

## How It Works

- **API Response Cache**: 5 minutes
- First request generates the response and caches it
- Subsequent requests are served instantly from cache
- Cache automatically expires after 5 minutes
- Next request regenerates and caches again

## Cache Duration

Current setting: **5 minutes** (300 seconds)

To adjust, edit `backend/api/views.py`:

```python
@method_decorator(cache_page(60 * 5), name='list')  # 60 * 5 = 5 minutes
class RankingsViewSet(viewsets.ReadOnlyModelViewSet):
```

Common durations:
- `60 * 1` = 1 minute (development)
- `60 * 5` = 5 minutes (default)
- `60 * 10` = 10 minutes (less frequent updates)
- `60 * 60` = 1 hour (very stable data)

## Manual Cache Clear

After updating data (running data ingestion jobs), clear the cache:

```bash
# Inside Docker
docker-compose exec backend python manage.py clear_cache

# Local development
python manage.py clear_cache
```

## Cache Backend

Currently using **LocMemCache** (in-memory, per-process).

For production with multiple workers, consider Redis:

```python
# settings.py
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://redis:6379/1',
    }
}
```

Then add Redis to `docker-compose.yml`.

## Benefits

✅ **Fast API responses**: Cached results served in <10ms  
✅ **Reduced database load**: No repeated queries for same data  
✅ **Simple**: Built into Django, no external dependencies  
✅ **Automatic expiration**: Data stays fresh  
✅ **Manual control**: Clear cache when data updates  

## Integration with Data Pipeline

Add cache clearing to your data processing jobs:

```python
# backend/api/job_tasks.py
from django.core.cache import cache

def run_update_all(job_id, season_year):
    # ... your existing code ...
    
    # Clear cache after successful update
    cache.clear()
    print("✓ Cache cleared")
```
