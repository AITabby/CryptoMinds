// CryptoMinds Service Worker — Web Push
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data.json(); } catch { data = { title: 'CryptoMinds', body: '新通知' }; }

  event.waitUntil(
    self.registration.showNotification(data.title || 'CryptoMinds', {
      body: data.body || '',
      icon: data.icon || '🔔',
      badge: '/badge.png',
      vibrate: [200, 100, 200],
      data: { url: data.url || '/' },
      actions: [
        { action: 'open', title: '查看' },
        { action: 'dismiss', title: '忽略' }
      ]
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  if (event.action === 'dismiss') return;
  event.waitUntil(
    clients.openWindow(event.notification.data.url || '/')
  );
});
