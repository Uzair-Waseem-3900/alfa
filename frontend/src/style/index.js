export * from './colors';
export * from './typography';
export * from './spacing';
export * from './shadows';
export * from './animations';
export * from './breakpoints';
export * from './transitions';

// Combine all theme tokens into a single object
export const theme = {
    colors: await import('./colors').then(m => m.colors),
    typography: await import('./typography').then(m => m.typography),
    spacing: await import('./spacing').then(m => m.spacing),
    shadows: await import('./shadows').then(m => m.shadows),
    animations: await import('./animations').then(m => m.animations),
    breakpoints: await import('./breakpoints').then(m => m.breakpoints),
    transitions: await import('./transitions').then(m => m.transitions),
};