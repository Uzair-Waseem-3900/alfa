export const breakpoints = {
    sm: '640px',
    md: '768px',
    lg: '1024px',
    xl: '1280px',
    '2xl': '1536px',
};

export const screens = {
    sm: { min: breakpoints.sm },
    md: { min: breakpoints.md },
    lg: { min: breakpoints.lg },
    xl: { min: breakpoints.xl },
    '2xl': { min: breakpoints['2xl'] },
};