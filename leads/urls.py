from django.urls import path

from . import views

urlpatterns = [
    path("", views.search, name="search"),
    path("health/", views.health, name="health"),
    path("jobs/<int:job_id>/", views.job_detail, name="job_detail"),
    path("jobs/<int:job_id>/leads/<int:lead_id>/", views.lead_detail, name="lead_detail"),
    path("jobs/<int:job_id>/export.json", views.export_json, name="export_json"),
    path("jobs/<int:job_id>/export.xlsx", views.export_excel, name="export_excel"),
]
