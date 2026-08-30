// Small helper shared by the Data Entry panels: pulls a field-specific
// message out of a DRF error response. Checks multiple possible field-name
// aliases because the write serializers use e.g. "supplier_id" while the
// service-layer ValidationErrors raised on top of them use "supplier" —
// same underlying field, different key depending on which layer rejected it.
export const getFieldError = (err, ...fieldNames) => {
    const data = err?.response?.data;
    if (!data || typeof data !== 'object') return undefined;
    for (const name of fieldNames) {
        const val = data[name];
        if (val != null) return Array.isArray(val) ? val[0] : val;
    }
    return undefined;
};
