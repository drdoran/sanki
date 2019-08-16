from django.urls import path
from danki import sync_app

# Anki Urls
urlpatterns = [

    # Sync Urls
    path('sync/hostKey', sync_app.hostKey),
    path('sync/meta', sync_app.SyncCollectionHandler.meta),
]
