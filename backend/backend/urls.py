from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from users.urls import auth_urlpatterns, user_urlpatterns
from backend.settings import PATH_ADMIN
from backend.views import PingView, TriggerAllCatchUpsView

urlpatterns = [
    path(f"{PATH_ADMIN}/", admin.site.urls),
    path("api/auth/",      include((auth_urlpatterns, "auth"))),
    path("api/users/",     include((user_urlpatterns, "users"))),
    path("api/",           include("purchases.urls")),     # categories, shelves, suppliers, products, orders, inventory
    path("api/rates/",     include("rates.urls")),
    path("api/billing/",   include("billing.urls")),
    path("api/cash-flow/", include("cash_flow.urls")),
    path("api/ledger/",    include("ledger.urls")),
    path("api/reports/",   include("reports.urls")),
    path("api/data-entry/", include("data_entry.urls")),
    path("api/taxes/",     include("taxes.urls")),
    path("api/cash-management/", include("cash_management.urls")),
    path("api/assets/", include("assets.urls")),
    path("api/recurring-expenses/", include("recurring_expenses.urls")),
    path("api/profits/", include("profits.urls")),
    path("api/backups/", include("backups.urls")),
    path("api/credit-score/", include("credit_score.urls")),
    path("api/activity-log/", include("activity_log.urls")),
    path("api/accounting/", include("accounting.urls")),
    path("api/payment-methods/", include("payment_methods.urls")),
    path("api/system/catch-up/", TriggerAllCatchUpsView.as_view(), name="trigger-all-catchups"),
    path("api/ping/", PingView.as_view(), name="ping"),
]
 
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)