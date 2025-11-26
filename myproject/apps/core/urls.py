from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload_pdf, name='upload_pdf'),
    path('rag/', views.simple_rag, name='rag_query'),
    path('rag-embedding/', views.embedding_rag_view, name='embedding_rag'),
    path('cadastrar/', views.manual_registration, name='manual_registration'),
    path('visualizar/', views.view_registrations, name='view_cadastros'),
    path('pesquisar/', views.search_registrations, name='api_search'),
    path('deletar/', views.delete_registration, name='api_delete'),
    path('editar/<str:item_type>/<int:item_id>/', views.edit_registration, name='edit_registration'),

]