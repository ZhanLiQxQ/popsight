/**
 * Six fixed retail aisles — matches backend `AmazonCategoryPreset` / `amazon_categories.py`.
 * Each row defines the SerpAPI keyword (`query`) and Amazon browse preset for /api/pipeline/amazon-ingest.
 */
export type AmazonCategoryPreset =
  | 'functional_health'
  | 'beverages'
  | 'snacks_confectionery'
  | 'grocery_staples'
  | 'personal_care_otc'
  | 'cultural_specialty';

export type AmazonCategoryRow = {
  preset: AmazonCategoryPreset;
  title: string;
  /** Short English aisle description (UI). */
  subtitle: string;
  /** Fixed SerpAPI search phrase for this aisle (tune here, no user search box). */
  query: string;
  maxProducts: number;
};

export const AMAZON_CATEGORY_ROWS: readonly AmazonCategoryRow[] = [
  {
    preset: 'functional_health',
    title: 'Functional Health',
    subtitle: 'Supplements & herbal SKUs',
    query: 'daily vitamin supplement',
    maxProducts: 12,
  },
  {
    preset: 'beverages',
    title: 'Beverages',
    subtitle: 'Bottled drinks & tea',
    query: 'zero sugar soda',
    maxProducts: 12,
  },
  {
    preset: 'snacks_confectionery',
    title: 'Snacks & Confectionery',
    subtitle: 'Packaged snacks & candy',
    query: 'protein snack bar',
    maxProducts: 12,
  },
  {
    preset: 'grocery_staples',
    title: 'Grocery Staples',
    subtitle: 'Pantry & packaged foods',
    query: 'organic pantry staples',
    maxProducts: 12,
  },
  {
    preset: 'personal_care_otc',
    title: 'Personal Care & OTC',
    subtitle: 'Household & OTC-style items',
    query: 'sensitive skin body wash',
    maxProducts: 12,
  },
  {
    preset: 'cultural_specialty',
    title: 'Cultural / Specialty',
    subtitle: 'International / specialty grocery',
    query: 'imported specialty food',
    maxProducts: 12,
  },
] as const;
