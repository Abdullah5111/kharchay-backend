from django.urls import path
from . import views

urlpatterns = [
    path("groups/<uuid:pk>/categories/", views.categories),
    path("groups/<uuid:pk>/expenses/", views.expenses),
    path("expenses/<uuid:pk>/", views.expense_detail),
    path("groups/<uuid:pk>/periods/", views.periods),
    path("groups/<uuid:pk>/periods/<str:ledger>/<int:year>/<int:month>/finalize/", views.finalize_period),
]
