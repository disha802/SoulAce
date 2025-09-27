// SoulAce Notification System
// Provides beautiful success/error popups and custom confirmation dialogs

// Create notification styles if not already added
if (!document.querySelector('#notification-styles')) {
  const styles = document.createElement('style');
  styles.id = 'notification-styles';
  styles.textContent = `
    /* Notification Container */
    .notification-container {
      position: fixed;
      top: 20px;
      right: 20px;
      z-index: 10000;
      pointer-events: none;
    }

    /* Notification Popup */
    .notification {
      background: white;
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 12px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
      border-left: 4px solid #ccc;
      max-width: 400px;
      transform: translateX(450px);
      transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
      pointer-events: auto;
      backdrop-filter: blur(10px);
      position: relative;
      overflow: hidden;
    }

    .notification.show {
      transform: translateX(0);
    }

    .notification.success {
      border-left-color: #4CAF50;
      background: linear-gradient(135deg, rgba(76, 175, 80, 0.1), rgba(255, 255, 255, 0.95));
    }

    .notification.error {
      border-left-color: #f44336;
      background: linear-gradient(135deg, rgba(244, 67, 54, 0.1), rgba(255, 255, 255, 0.95));
    }

    .notification.info {
      border-left-color: #2196F3;
      background: linear-gradient(135deg, rgba(33, 150, 243, 0.1), rgba(255, 255, 255, 0.95));
    }

    .notification.warning {
      border-left-color: #ff9800;
      background: linear-gradient(135deg, rgba(255, 152, 0, 0.1), rgba(255, 255, 255, 0.95));
    }

    .notification-header {
      display: flex;
      align-items: center;
      margin-bottom: 4px;
    }

    .notification-icon {
      font-size: 20px;
      margin-right: 12px;
      line-height: 1;
    }

    .notification-title {
      font-weight: 600;
      font-size: 14px;
      color: #333;
      margin: 0;
    }

    .notification-message {
      font-size: 13px;
      color: #666;
      line-height: 1.4;
      margin: 0;
      padding-left: 32px;
    }

    .notification-close {
      position: absolute;
      top: 8px;
      right: 8px;
      background: none;
      border: none;
      font-size: 18px;
      color: #999;
      cursor: pointer;
      padding: 4px;
      border-radius: 50%;
      width: 24px;
      height: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .notification-close:hover {
      background: rgba(0, 0, 0, 0.1);
      color: #666;
    }

    /* Progress bar */
    .notification-progress {
      position: absolute;
      bottom: 0;
      left: 0;
      height: 3px;
      background: rgba(0, 0, 0, 0.1);
      border-radius: 0 0 12px 12px;
      overflow: hidden;
    }

    .notification-progress-bar {
      height: 100%;
      background: linear-gradient(90deg, #4CAF50, #45a049);
      transform-origin: left;
      animation: notificationProgress 7s linear forwards;
    }

    .notification.error .notification-progress-bar {
      background: linear-gradient(90deg, #f44336, #d32f2f);
    }

    .notification.warning .notification-progress-bar {
      background: linear-gradient(90deg, #ff9800, #f57c00);
    }

    .notification.info .notification-progress-bar {
      background: linear-gradient(90deg, #2196F3, #1976D2);
    }

    @keyframes notificationProgress {
      from { transform: scaleX(1); }
      to { transform: scaleX(0); }
    }

    /* Custom Confirmation Dialog */
    .custom-confirm-overlay {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.5);
      backdrop-filter: blur(4px);
      z-index: 15000;
      display: flex;
      align-items: center;
      justify-content: center;
      opacity: 0;
      transition: opacity 0.3s ease;
    }

    .custom-confirm-overlay.show {
      opacity: 1;
    }

    .custom-confirm-dialog {
      background: white;
      border-radius: 16px;
      padding: 24px;
      max-width: 400px;
      width: 90%;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
      transform: scale(0.9) translateY(20px);
      transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
    }

    .custom-confirm-overlay.show .custom-confirm-dialog {
      transform: scale(1) translateY(0);
    }

    .custom-confirm-icon {
      font-size: 48px;
      text-align: center;
      margin-bottom: 16px;
    }

    .custom-confirm-title {
      font-size: 18px;
      font-weight: 600;
      text-align: center;
      margin-bottom: 8px;
      color: #333;
    }

    .custom-confirm-message {
      font-size: 14px;
      text-align: center;
      color: #666;
      margin-bottom: 24px;
      line-height: 1.5;
    }

    .custom-confirm-buttons {
      display: flex;
      gap: 12px;
      justify-content: center;
    }

    .custom-confirm-btn {
      padding: 12px 24px;
      border: none;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
      min-width: 80px;
    }

    .custom-confirm-btn.primary {
      background: #c17b6b;
      color: white;
    }

    .custom-confirm-btn.primary:hover {
      background: #a86b5b;
      transform: translateY(-1px);
    }

    .custom-confirm-btn.secondary {
      background: #f5f5f5;
      color: #666;
    }

    .custom-confirm-btn.secondary:hover {
      background: #e0e0e0;
      transform: translateY(-1px);
    }

    /* Dark mode support */
    body.dark .notification {
      background: linear-gradient(135deg, rgba(42, 42, 42, 0.95), rgba(60, 60, 60, 0.95));
      color: #e0e0e0;
    }

    body.dark .notification-title {
      color: #e0e0e0;
    }

    body.dark .notification-message {
      color: #b0b0b0;
    }

    body.dark .custom-confirm-dialog {
      background: #2a2a2a;
      color: #e0e0e0;
    }

    body.dark .custom-confirm-title {
      color: #e0e0e0;
    }

    body.dark .custom-confirm-message {
      color: #b0b0b0;
    }

    /* Mobile responsive */
    @media (max-width: 768px) {
      .notification-container {
        top: 10px;
        right: 10px;
        left: 10px;
      }

      .notification {
        max-width: none;
        transform: translateY(-100px);
      }

      .notification.show {
        transform: translateY(0);
      }

      .custom-confirm-dialog {
        margin: 20px;
        width: calc(100% - 40px);
      }
    }
  `;
  document.head.appendChild(styles);
}

// Create notification container
function createNotificationContainer() {
  let container = document.querySelector('.notification-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'notification-container';
    document.body.appendChild(container);
  }
  return container;
}

// Show notification function
function showNotification(message, type = 'info', duration = 7000, title = null) {
  const container = createNotificationContainer();

  const notification = document.createElement('div');
  notification.className = `notification ${type}`;

  const icons = {
    success: '✅',
    error: '❌',
    warning: '⚠️',
    info: 'ℹ️'
  };

  const titles = {
    success: title || 'Success',
    error: title || 'Error',
    warning: title || 'Warning',
    info: title || 'Info'
  };

  notification.innerHTML = `
    <button class="notification-close" onclick="this.parentElement.remove()">×</button>
    <div class="notification-header">
      <span class="notification-icon">${icons[type]}</span>
      <h4 class="notification-title">${titles[type]}</h4>
    </div>
    <p class="notification-message">${message}</p>
    <div class="notification-progress">
      <div class="notification-progress-bar"></div>
    </div>
  `;

  container.appendChild(notification);

  // Trigger animation
  setTimeout(() => notification.classList.add('show'), 10);

  // Auto remove
  const timeout = setTimeout(() => {
    notification.style.transform = 'translateX(450px)';
    setTimeout(() => notification.remove(), 400);
  }, duration);

  // Clear timeout if manually closed
  notification.querySelector('.notification-close').addEventListener('click', () => {
    clearTimeout(timeout);
  });

  return notification;
}

// Custom confirmation dialog
function showConfirmDialog(message, title = 'Confirm Action', confirmText = 'Confirm', cancelText = 'Cancel') {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'custom-confirm-overlay';

    overlay.innerHTML = `
      <div class="custom-confirm-dialog">
        <div class="custom-confirm-icon">⚠️</div>
        <h3 class="custom-confirm-title">${title}</h3>
        <p class="custom-confirm-message">${message}</p>
        <div class="custom-confirm-buttons">
          <button class="custom-confirm-btn secondary" data-action="cancel">${cancelText}</button>
          <button class="custom-confirm-btn primary" data-action="confirm">${confirmText}</button>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    // Show with animation
    setTimeout(() => overlay.classList.add('show'), 10);

    // Handle button clicks
    overlay.addEventListener('click', (e) => {
      if (e.target.dataset.action === 'confirm') {
        resolve(true);
        closeDialog();
      } else if (e.target.dataset.action === 'cancel' || e.target === overlay) {
        resolve(false);
        closeDialog();
      }
    });

    function closeDialog() {
      overlay.classList.remove('show');
      setTimeout(() => overlay.remove(), 300);
    }

    // ESC key to close
    const handleEsc = (e) => {
      if (e.key === 'Escape') {
        resolve(false);
        closeDialog();
        document.removeEventListener('keydown', handleEsc);
      }
    };
    document.addEventListener('keydown', handleEsc);
  });
}

// Convenience functions
window.showSuccess = (message, title) => showNotification(message, 'success', 7000, title);
window.showError = (message, title) => showNotification(message, 'error', 7000, title);
window.showWarning = (message, title) => showNotification(message, 'warning', 7000, title);
window.showInfo = (message, title) => showNotification(message, 'info', 7000, title);
window.showConfirm = showConfirmDialog;

// Replace alert function
window.alert = function(message) {
  showError(message, 'Alert');
};

// Replace confirm function
window.confirm = function(message) {
  return showConfirmDialog(message);
};