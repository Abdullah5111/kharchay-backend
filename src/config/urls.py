from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.social.urls")),
    path("api/", include("apps.ledger.urls")),
    path("api/", include("apps.notifications.urls")),
    path("api/", include("apps.haazri.urls")),
    path("api/", include("apps.settlement.urls")),
    path("api/", include("apps.payments.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
