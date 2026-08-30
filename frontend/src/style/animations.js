// Remove the import { Variants } from 'framer-motion' - it's not needed

export const animations = {
    // Page transitions
    pageTransition: {
        initial: { opacity: 0, y: 20 },
        animate: { opacity: 1, y: 0 },
        exit: { opacity: 0, y: -20 },
        transition: { duration: 0.3, ease: 'easeInOut' },
    },

    // Fade animations
    fadeIn: {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        exit: { opacity: 0 },
        transition: { duration: 0.4 },
    },

    fadeInUp: {
        initial: { opacity: 0, y: 30 },
        animate: { opacity: 1, y: 0 },
        exit: { opacity: 0, y: -30 },
        transition: { duration: 0.5, ease: 'easeOut' },
    },

    fadeInDown: {
        initial: { opacity: 0, y: -30 },
        animate: { opacity: 1, y: 0 },
        exit: { opacity: 0, y: 30 },
        transition: { duration: 0.5, ease: 'easeOut' },
    },

    fadeInLeft: {
        initial: { opacity: 0, x: -30 },
        animate: { opacity: 1, x: 0 },
        exit: { opacity: 0, x: 30 },
        transition: { duration: 0.5, ease: 'easeOut' },
    },

    fadeInRight: {
        initial: { opacity: 0, x: 30 },
        animate: { opacity: 1, x: 0 },
        exit: { opacity: 0, x: -30 },
        transition: { duration: 0.5, ease: 'easeOut' },
    },

    // Scale animations
    scaleIn: {
        initial: { opacity: 0, scale: 0.9 },
        animate: { opacity: 1, scale: 1 },
        exit: { opacity: 0, scale: 0.9 },
        transition: { duration: 0.3, ease: 'easeOut' },
    },

    scaleUp: {
        initial: { opacity: 0, scale: 0.5 },
        animate: { opacity: 1, scale: 1 },
        exit: { opacity: 0, scale: 0.5 },
        transition: { duration: 0.4, ease: 'easeOut' },
    },

    // Slide animations
    slideIn: {
        initial: { x: '100%' },
        animate: { x: 0 },
        exit: { x: '100%' },
        transition: { duration: 0.3, ease: 'easeInOut' },
    },

    slideUp: {
        initial: { y: '100%' },
        animate: { y: 0 },
        exit: { y: '100%' },
        transition: { duration: 0.3, ease: 'easeInOut' },
    },

    // Stagger children
    staggerContainer: {
        animate: {
            transition: {
                staggerChildren: 0.1,
                delayChildren: 0.2,
            },
        },
    },

    staggerItem: {
        initial: { opacity: 0, y: 20 },
        animate: { opacity: 1, y: 0 },
        exit: { opacity: 0, y: -20 },
        transition: { duration: 0.4 },
    },

    // Hover animations
    hoverScale: {
        whileHover: { scale: 1.05 },
        whileTap: { scale: 0.95 },
        transition: { duration: 0.2 },
    },

    hoverGlow: {
        whileHover: {
            boxShadow: '0 0 20px rgba(99, 102, 241, 0.3)',
            transition: { duration: 0.3 },
        },
    },

    // Loading skeleton animation
    shimmer: {
        animate: {
            backgroundPosition: ['200% 0', '-200% 0'],
            transition: {
                duration: 1.5,
                repeat: Infinity,
                repeatType: 'loop',
            },
        },
    },

    // Notification animations
    notificationSlide: {
        initial: { x: '100%', opacity: 0 },
        animate: { x: 0, opacity: 1 },
        exit: { x: '100%', opacity: 0 },
        transition: { duration: 0.4, ease: 'easeOut' },
    },

    // Modal animations
    modalOverlay: {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        exit: { opacity: 0 },
        transition: { duration: 0.2 },
    },

    modalContent: {
        initial: { opacity: 0, scale: 0.9, y: 20 },
        animate: { opacity: 1, scale: 1, y: 0 },
        exit: { opacity: 0, scale: 0.9, y: 20 },
        transition: { duration: 0.3, ease: 'easeOut' },
    },

    // List animations
    listItem: {
        initial: { opacity: 0, x: -20 },
        animate: { opacity: 1, x: 0 },
        exit: { opacity: 0, x: 20 },
        transition: { duration: 0.3 },
    },

    // Card flip animation
    cardFlip: {
        initial: { rotateY: 0 },
        animate: { rotateY: 180 },
        transition: { duration: 0.6 },
    },
};

// Export animation variants for framer-motion
export const pageVariants = animations.pageTransition;
export const fadeInVariants = animations.fadeInUp;
export const staggerVariants = animations.staggerContainer;