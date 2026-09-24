import { useId } from 'react';

import { BOOK_STATUSES } from '../../api/schemas';
import { STATUS_LABELS } from '../../lib/format';

import type { StatusFilterValue } from './queryKeys';

interface StatusFilterProps {
  value: StatusFilterValue;
  onChange: (value: StatusFilterValue) => void;
}

const OPTIONS: { value: StatusFilterValue; label: string }[] = [
  { value: undefined, label: 'All' },
  ...BOOK_STATUSES.map((s) => ({ value: s, label: STATUS_LABELS[s] })),
];

/** Segmented control built on native radios: arrow-key navigation and semantics for free. */
export function StatusFilter({ value, onChange }: StatusFilterProps) {
  const name = useId();
  return (
    <fieldset className="segmented">
      <legend>Filter by status</legend>
      <div className="segmented-options">
        {OPTIONS.map((option) => (
          <label key={option.label} className="segment">
            <input
              type="radio"
              name={name}
              value={option.value ?? 'all'}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
