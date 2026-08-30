// Extracts a human-readable message from a DRF-style API error. Responses are
// either {detail: "..."} / {detail: [...]}, a field-validation shape
// ({field_name: ["msg", ...]}), or a plain string body.
export const extractErrorMessage = (error, fallback = 'Something went wrong') => {
    const data = error?.response?.data;
    if (!data) return error?.message || fallback;
    if (typeof data === 'string') return data;
    if (data.detail) return Array.isArray(data.detail) ? data.detail[0] : data.detail;
    const firstKey = Object.keys(data)[0];
    if (firstKey) {
        const val = data[firstKey];
        return Array.isArray(val) ? val[0] : val;
    }
    return fallback;
};
