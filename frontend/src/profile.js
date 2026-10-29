import { api } from './api';

export const GRADES = [5, 6, 7, 8, 9, 10, 11];

export const FEDERAL_REGIONS = new Set(['Москва', 'Санкт-Петербург', 'Севастополь']);

export async function federalCity(region) {
  if (!FEDERAL_REGIONS.has(region)) return null;
  try {
    const [city] = await api.cities(region, '');
    if (city) return { id: city.id, name: city.name };
  } catch {
  }
  return { id: null, name: region };
}

export const clean = (text) => text.trim().replace(/\s+/g, ' ');

export const place = (id, name) => (name && typeof name === 'string' ? { id: id ?? null, name } : null);

export const placeFields = (key, value) => {
  if (!value) return {};
  return value.id ? { [`${key}_id`]: value.id } : { [key]: clean(value.name) };
};

export const samePlace = (a, b) => (a?.id ?? null) === (b?.id ?? null) && clean(a?.name ?? '') === clean(b?.name ?? '');
