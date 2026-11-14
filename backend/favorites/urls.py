from django.urls import path

from .views import FavoritesView

urlpatterns = [
    path("", FavoritesView.as_view(), name="favorites"),
]
