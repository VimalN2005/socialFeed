import os
from pathlib import Path
from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

def serve_frontend_index(request):
    html_file = BASE_DIR / 'frontend' / 'index.html'
    if html_file.exists():
        return HttpResponse(html_file.read_text(encoding='utf-8'), content_type='text/html')
    return HttpResponse("<h1>ScaleFeed API Engine Running</h1>", content_type='text/html')

def serve_frontend_app_js(request):
    js_file = BASE_DIR / 'frontend' / 'app.js'
    if js_file.exists():
        return HttpResponse(js_file.read_text(encoding='utf-8'), content_type='application/javascript')
    return HttpResponse("// app.js not found", content_type='application/javascript')

urlpatterns = [
    # Frontend Single Page App Routes (Works out-of-the-box on Render, Docker, or local)
    path('', serve_frontend_index, name='frontend_index'),
    path('app.js', serve_frontend_app_js, name='frontend_app_js'),

    path('admin/', admin.site.urls),
    
    # Authentication & JWT Endpoints
    path('api/v1/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # App Routes
    path('api/v1/users/', include('apps.users.urls')),
    path('api/v1/posts/', include('apps.posts.urls')),
    path('api/v1/feed/', include('apps.feed.urls')),
]
