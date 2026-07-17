// Gestione globale degli effetti dell'interfaccia utente

document.addEventListener('DOMContentLoaded', () => {
    // Fai sparire automaticamente i messaggi flash dopo 5 secondi
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(message => {
        setTimeout(() => {
            // Effetto fade-out prima di rimuovere l'elemento
            message.style.transition = 'opacity 0.5s ease-out, transform 0.5s ease-out';
            message.style.opacity = '0';
            message.style.transform = 'translateY(-10px)';
            setTimeout(() => {
                message.remove();
            }, 500);
        }, 5000);
    });
});
