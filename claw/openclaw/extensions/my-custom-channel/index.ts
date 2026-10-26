import { PluginApi, InboundMessage } from '@openclaw/sdk';


export default {
  id: "my-custom-channel", register(api) {
    async function getRawBody(req: any): Promise<string> {
      return new Promise((resolve, reject) => {
        let body = '';
        req.on('data', (chunk: Buffer) => {
          body += chunk.toString();
        });
        req.on('end', () => {
          resolve(body);
        });
        req.on('error', (err: Error) => {
          reject(err);
        });
      });
    }

    api.registerHttpRoute({ path: "/demo", handler: async (_req, res) => { res.statusCode = 200; res.end("ok"); } });

    // 1. Register the Webhook Route
    // This creates an endpoint at http://your-gateway:18789/hooks/custom-webhook
    api.registerHttpRoute({ path: '/custom-webhook',  handler: async (_req, res) => {
      console.log(_req);
      // 1. Read the raw body from the IncomingMessage stream
      const rawBody = await getRawBody(_req);

      // 2. Parse the JSON
      const data = JSON.parse(rawBody);
      const {senderId, senderName, text, conversationId } = data;
      console.log(data)
      // const { senderId, senderName, text, conversationId } = _req.body;

      if (_req.method !== 'POST') {
        return res.status(405).send({
          error: 'Method Not Allowed',
          message: `This endpoint requires POST. Received: ${_req.method}`
        });
      }

      if (!text || !senderId) {
        return res.status(400).send({ error: 'Missing required fields' });
      }

      // 2. Format the message for OpenClaw
      const inbound: InboundMessage = {
        channel: 'custom-webhook',
        accountId: 'default',
        messageId: `msg-${Date.now()}`,
        sender: {
          id: senderId,
          name: senderName || 'External User',
        },
        conversation: {
          id: conversationId || senderId, // Treat DMs as conversation ID
          type: 'direct',
        },
        content: {
          text: text,
        },
      };

      console.log(api.runtime.messages);
      // 3. Send to OpenClaw's internal message bus
      await api.runtime.messages.inbound(inbound);

      res.status(200).send({ status: 'received' });
    }});
  }
};
// export default function (api: PluginApi) {

//   // 1. Register the Webhook Route
//   // This creates an endpoint at http://your-gateway:18789/hooks/custom-webhook
//   api.registerHttpRoute('post', '/hooks/custom-webhook', async (req, res) => {
//     const { senderId, senderName, text, conversationId } = req.body;

//     if (!text || !senderId) {
//       return res.status(400).send({ error: 'Missing required fields' });
//     }

//     // 2. Format the message for OpenClaw
//     const inbound: InboundMessage = {
//       channel: 'custom-webhook',
//       accountId: 'default',
//       messageId: `msg-${Date.now()}`,
//       sender: {
//         id: senderId,
//         name: senderName || 'External User',
//       },
//       conversation: {
//         id: conversationId || senderId, // Treat DMs as conversation ID
//         type: 'direct',
//       },
//       content: {
//         text: text,
//       },
//     };

//     // 3. Send to OpenClaw's internal message bus
//     await api.runtime.messages.inbound(inbound);

//     res.status(200).send({ status: 'received' });
//   });

//   // 4. Handle Outbound Messages (AI responding back to the user)
//   api.registerHook('onOutboundMessage', async (msg) => {
//     if (msg.channel !== 'custom-webhook') return;

//     // Here you would call your external service's API to deliver the AI's reply
//     console.log(`Sending reply to ${msg.recipient.id}: ${msg.content.text}`);

//     /* Example:
//     await fetch('https://your-external-service.com/api/send', {
//       method: 'POST',
//       body: JSON.stringify({ to: msg.recipient.id, text: msg.content.text })
//     });
//     */
//   });
// }