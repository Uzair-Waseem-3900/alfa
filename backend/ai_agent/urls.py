from django.urls import path

from . import views

urlpatterns = [
    path("chats/", views.ChatListCreateView.as_view(), name="agent-chats"),
    path("chats/<uuid:chat_id>/", views.ChatDetailView.as_view(), name="agent-chat-detail"),
    path("chats/<uuid:chat_id>/messages/", views.ChatMessagesView.as_view(), name="agent-chat-messages"),
    path("team/users/", views.TeamOwnersView.as_view(), name="agent-team-users"),
    path("team/users/<str:email>/chats/", views.TeamUserChatsView.as_view(), name="agent-team-user-chats"),
    path("team/chats/<uuid:chat_id>/", views.TeamChatDetailView.as_view(), name="agent-team-chat"),
    path("team/chats/<uuid:chat_id>/messages/", views.TeamChatMessagesView.as_view(), name="agent-team-messages"),
    path("runs/<uuid:run_id>/stream/", views.run_stream, name="agent-run-stream"),
]
