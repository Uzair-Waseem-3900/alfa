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
    path("bulk/link-names/", views.BulkLinkNamesView.as_view(), name="agent-bulk-link-names"),
    path("bulk/batches/", views.BulkBatchListCreateView.as_view(), name="agent-bulk-batches"),
    path("bulk/batches/<uuid:batch_id>/", views.BulkBatchDetailView.as_view(), name="agent-bulk-batch"),
    path("bulk/batches/<uuid:batch_id>/cancel/", views.BulkCancelView.as_view(), name="agent-bulk-cancel"),
    path("bulk/batches/<uuid:batch_id>/stream/", views.bulk_stream, name="agent-bulk-stream"),
    path("bulk/items/<int:item_id>/answer/", views.BulkAnswerView.as_view(), name="agent-bulk-answer"),
    path("bulk/items/<int:item_id>/skip/", views.BulkSkipView.as_view(), name="agent-bulk-skip"),
    path("bulk/items/<int:item_id>/retry/", views.BulkRetryView.as_view(), name="agent-bulk-retry"),
    path("runs/<uuid:run_id>/stream/", views.run_stream, name="agent-run-stream"),
]
