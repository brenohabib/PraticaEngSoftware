from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload_pdf, name='upload_pdf'),
    path('rag/', views.simple_rag, name='rag_query'),
    path('rag-embedding/', views.embedding_rag_view, name='embedding_rag'),
    path('cadastrar/', views.manual_registration, name='manual_registration'),
    path('visualizar/', views.view_registrations, name='view_cadastros'),
]