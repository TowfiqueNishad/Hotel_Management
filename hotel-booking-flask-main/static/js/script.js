// Custom JavaScript for Flask Web App

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips if Bootstrap is available
    if (typeof bootstrap !== 'undefined') {
        var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
        var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl)
        })
    }

    // Flash message auto-dismiss
    const flashMessages = document.querySelectorAll('.alert');
    flashMessages.forEach(function(message) {
        setTimeout(function() {
            // Create fade out effect
            message.style.transition = 'opacity 1s';
            message.style.opacity = '0';
            
            // Remove element after fade out
            setTimeout(function() {
                message.remove();
            }, 1000);
        }, 5000); // 5 seconds before starting to fade
    });

    // Form validation enhancement
    const forms = document.querySelectorAll('form');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
                
                // Highlight all invalid fields
                const invalidFields = form.querySelectorAll(':invalid');
                invalidFields.forEach(function(field) {
                    field.classList.add('is-invalid');
                    
                    // Add event listener to remove invalid class when user starts typing
                    field.addEventListener('input', function() {
                        field.classList.remove('is-invalid');
                    }, { once: true });
                });
            }
            
            form.classList.add('was-validated');
        }, false);
    });

    // Add smooth scrolling to all links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();

            const targetId = this.getAttribute('href');
            if (targetId === '#') return;
            
            const targetElement = document.querySelector(targetId);
            if (targetElement) {
                targetElement.scrollIntoView({
                    behavior: 'smooth'
                });
            }
        });
    });
});