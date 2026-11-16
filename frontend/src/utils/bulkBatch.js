const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

// The label a bulk batch gets until the user renames it, e.g. "3 invoices · FSD".
export const defaultBatchLabel = (b) => `${plural(b.total, 'invoice')}${b.link_name_label ? ` · ${b.link_name_label}` : ''}`;
