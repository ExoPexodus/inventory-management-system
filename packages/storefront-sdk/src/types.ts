// ---------------------------------------------------------------------------
// Shared
// ---------------------------------------------------------------------------

export interface ApiError {
  detail: string;
}

// ---------------------------------------------------------------------------
// Catalog
// ---------------------------------------------------------------------------

export interface StorefrontProductImage {
  url: string;
  alt_text: string | null;
  sort_order: number;
}

export interface StorefrontProduct {
  id: string;
  name: string;
  slug: string | null;
  subtitle: string | null;
  ribbon: string | null;
  description: string | null;
  short_description: string | null;
  product_type: string;
  status: string;
  sku: string;
  unit_price_cents: number;
  discount_price_cents: number | null;
  currency_code: string;
  image_url: string | null;
  images: StorefrontProductImage[] | null;  // null in list responses, populated in detail
  tags: string[] | null;
  track_quantity: boolean;
  weight_grams: number | null;
  meta_title: string | null;
  meta_description: string | null;
}

export interface ProductList {
  items: StorefrontProduct[];
  total: number;
  page: number;
  per_page: number;
}

// ---------------------------------------------------------------------------
// Cart
// ---------------------------------------------------------------------------

export interface CartItem {
  id: string;
  product_id: string;
  product_name: string;
  quantity: number;
  unit_price_cents: number;
  line_total_cents: number;
  currency_code: string;
}

export interface Cart {
  cart_token: string;
  channel_id: string;
  items: CartItem[];
  subtotal_cents: number;
  total_cents: number;
  currency_code: string;
}

export interface CartSummary {
  cart_token: string;
  subtotal_cents: number;
  discount_cents: number;
  tax_cents: number;
  shipping_cents: number;
  total_cents: number;
  currency_code: string;
  discount_code: string | null;
}

export interface DiscountApplyResult {
  cart_token: string;
  discount_code: string;
  discount_type: string;
  discount_cents: number;
  final_subtotal_cents: number;
  is_free_shipping: boolean;
}

// ---------------------------------------------------------------------------
// Checkout (hosted)
// ---------------------------------------------------------------------------

export interface CheckoutSession {
  session_token: string;
  checkout_url: string;
  expires_at: string;
}

export interface PaymentIntentResult {
  provider: string;
  payment_intent_id?: string;
  client_secret?: string;
  order_id?: string;
  key_id?: string;
  amount?: number;
  currency?: string;
}

export interface CheckoutCompleteResult {
  status: string;
  order_id: string;
  redirect_url: string;
}

// ---------------------------------------------------------------------------
// Order (direct submit)
// ---------------------------------------------------------------------------

export interface SubmitOrderPayload {
  cart_token: string;
  payment_provider: string;
  payment_reference: string;
  customer_email?: string;
  customer_phone?: string;
  shipping_address?: Record<string, string>;
  billing_address?: Record<string, string>;
  discount_code?: string;
}

export interface SubmittedOrder {
  id: string;
  channel_id: string;
  status: string;
  customer_email: string | null;
  subtotal_cents: number;
  discount_cents: number;
  tax_cents: number;
  shipping_cents: number;
  total_cents: number;
  currency_code: string;
}

// ---------------------------------------------------------------------------
// Auth (OTP)
// ---------------------------------------------------------------------------

export interface OTPRequestResult {
  sent: boolean;
  message: string;
}

export interface OTPVerifyResult {
  access_token: string;
  token_type: string;
  expires_in: number;
}

// ---------------------------------------------------------------------------
// Customer portal
// ---------------------------------------------------------------------------

export interface CustomerProfile {
  email: string;
  name: string | null;
  customer_id: string | null;
}

export interface CustomerOrderLine {
  title: string;
  sku: string | null;
  quantity: number;
  unit_price_cents: number;
  line_total_cents: number;
}

export interface CustomerOrder {
  id: string;
  status: string;
  total_cents: number;
  currency_code: string;
  placed_at: string;
  lines: CustomerOrderLine[];
}
