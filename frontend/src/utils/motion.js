// Shared motion language for the assistant + bulk-invoice screens, so every
// piece of the agent UI moves with the same physics. framer-motion only; the
// reduced-motion switch is global (<MotionConfig reducedMotion="user"> in App).
//
// RULE: animate opacity/transform on LEAF elements only. Never put a transform,
// filter or will-change on a wrapper that contains `position: fixed` children
// (sidebar drawer, dialogs) — it turns the wrapper into their containing block.

export const SPRING_SOFT  = { type: 'spring', stiffness: 260, damping: 28 };
export const SPRING_SNAPPY = { type: 'spring', stiffness: 420, damping: 30 };
export const SPRING_POP   = { type: 'spring', stiffness: 520, damping: 24 };
export const EASE_OUT     = [0.22, 1, 0.36, 1];   // expo-ish: fast start, long soft landing

// Container that staggers its children in. Cap the delay so long lists never feel slow.
export const stagger = (step = 0.05, delay = 0) => ({
    hidden: {},
    show: { transition: { staggerChildren: step, delayChildren: delay } },
});

// A block rising into place.
export const rise = {
    hidden: { opacity: 0, y: 14 },
    show:   { opacity: 1, y: 0, transition: { duration: 0.45, ease: EASE_OUT } },
};

// Page-level choreography for the full-screen agent pages: each region enters on
// its own cue (sidebar, header, body, composer), so the screen "assembles".
export const region = (from, delay = 0) => ({
    hidden: { opacity: 0, ...from },
    show:   { opacity: 1, x: 0, y: 0, transition: { duration: 0.5, ease: EASE_OUT, delay } },
});
