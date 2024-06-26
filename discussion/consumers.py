from channels.db import database_sync_to_async
from django.db.models import Q

from ProjectOpenDebate.consumers import CustomBaseConsumer, get_user_group_name
from .forms import MessageForm
from .models import Discussion


class MessageConsumer(CustomBaseConsumer):
    """
    This consumer handles the WebSocket connection for the sending and receiving of messages in discussions.
    """

    @database_sync_to_async
    def save_message_to_db(self, user, discussion_id: int, message_text: str):
        messageForm = MessageForm({'text': message_text})

        if messageForm.is_valid():
            message = messageForm.save(commit=False)
            message.discussion_id = discussion_id
            message.author = user
            message.save()
            return True
        else:
            return False

    async def receive_json(self, content, **kwargs):
        """
        Receives a JSON message from the client and processes it.
        Note: all the data here is untrusted, so we should validate it before processing it.

        :param content: The JSON message from the client
        :param kwargs: Additional arguments
        """
        # Get the data from the content
        data = content.get('data', {})

        # check that we have an integer discussion_id and an event_type
        discussion_id = data.get('discussion_id')
        event_type = str(content.get('event_type', ''))
        if not isinstance(discussion_id, int) or not event_type:
            await self.send_json({'status': 'error', 'message': 'Missing discussion_id or event_type'})
            return

        # Get the user from the scope
        user = self.scope['user']

        # check that the user is a participant in the discussion
        try:
            discussion = await database_sync_to_async(Discussion.objects.get)(
                Q(participant1=user) | Q(participant2=user),
                id=discussion_id
            )
        except Discussion.DoesNotExist:
            await self.send_json({'status': 'error', 'message': 'You are not a participant in this discussion'})
            return

        # Process the event according to the event_type
        if event_type == 'new_message':
            await self.process_new_message(user, discussion, data)
        else:
            await self.send_json({'status': 'error', 'message': 'Invalid event_type'})

    async def process_new_message(self, user, discussion, data):
        # Check that the message exists
        message = data.get('message', '').strip()
        if not message:
            await self.send_json({'status': 'error', 'message': 'Missing message'})
            return

        # save the message to the database
        is_valid_message = await self.save_message_to_db(user, discussion.id, message)

        # Send error message if the message is invalid
        if not is_valid_message:
            await self.send_json({'status': 'error', 'message': 'Invalid message'})
            return

        # Send the message to all participants in the discussion
        participants_ids = [discussion.participant1_id, discussion.participant2_id]
        for participant_id in participants_ids:
            user_group_name = get_user_group_name(self.__class__.__name__, participant_id)
            await self.channel_layer.group_send(
                user_group_name,
                {
                    'status': 'success',
                    'event_type': 'new_message',
                    'type': 'send.json',
                    'data': {
                        'discussion_id': discussion.id,
                        'sender_id': user.id,
                        'sender': user.username,
                        'message': message,
                    }
                }
            )


class DiscussionConsumer(CustomBaseConsumer):
    """
    This consumer handles the WebSocket connection for CRUD operations on discussions.

    TODO: For now, this consumer is completely empty. However, once we implement the logic for creating, updating,
        and deleting discussions, this class will make more sense. Or maybe do we want to merge this with the
        MessageConsumer that would handle all the CRUD operations for discussions AND messages?
    """

    async def receive_json(self, content, **kwargs):
        """
        Receives a JSON message from the client and processes it.
        Note: all the data here is untrusted, so we should validate it before processing it.

        :param content: The JSON message from the client
        :param kwargs: Additional arguments
        """
        # For now, the clients cant send any messages to this consumer
        # This is because the discussion are created by the server once a discussion request is filled
        # Therefore, it wouldnt make sense for the client to create a discussion by sending a message here
        # However, if we decide to allow clients to modify, delete discussions, we will add the logic here
        pass
