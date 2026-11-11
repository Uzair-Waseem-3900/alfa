from django.urls import path

from . import views

urlpatterns = [
    path("chats/", views.ChatListCreateView.as_view(), name="agent-chats"),
    path("chats/<uuid:chat_id>/", views.ChatDetailView.as_view(), name="agent-chat-detail"),
    path("chats/<uuid:chat_id>/messages/", views.ChatMessagesView.as_view(), name="agent-chat-messages"),
    path("runs/<uuid:run_id>/stream/", views.run_stream, name="agent-run-stream"),
]
