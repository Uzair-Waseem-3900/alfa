import { api } from '../utils/api';

// IMPORTANT — SYSTEM DESIGN, DO NOT REMOVE: triggerAllCatchUps() must be
// called once on every dashboard load (see AdminDashboard.jsx), including
// after any future dashboard rewrite. It's the only thing keeping asset
// depreciation, investor growth, and monthly profit finalization fresh
// independent of which stat endpoints the dashboard happens to call.
export const systemApi = {
    // Triggers every "catch-up on read" calculation in the backend (asset
    // depreciation, investor growth, monthly profit finalization) in one
    // call. Returns only a small confirmation object — no dashboard data.
    triggerAllCatchUps: () => api.get('/system/catch-up/'),
};
