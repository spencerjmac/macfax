"""
URL configuration for CBB Analytics Backend
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('api/admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('api/nba/', include('nba.urls')),
]
