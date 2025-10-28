// Define stub BEFORE loading Cal's embed.js
window.Cal = window.Cal || function () {
  (window.Cal.q = window.Cal.q || []).push(arguments);
};

// Load Cal script dynamically, then init
(function () {
  var s = document.createElement('script');
  s.src = 'https://app.cal.com/embed/embed.js';
  s.onload = function () {
    try {
      window.Cal('ui', { theme: 'light' });
      console.log('Cal ready.');
    } catch (e) {
      console.error('Cal init error:', e);
    }
  };
  s.onerror = function () {
    console.error('Failed to load Cal embed.js');
  };
  document.head.appendChild(s);
})();
