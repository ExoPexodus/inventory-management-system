import type {
  ApiError,
  Cart,
  CartSummary,
  CheckoutCompleteResult,
  CheckoutSession,
  CustomerOrder,
  CustomerProfile,
  DiscountApplyResult,
  MagicLinkRequestResponse,
  MagicLinkVerifyResponse,
  OTPRequestResult,
  OTPVerifyResult,
  PaymentIntentResult,
  ProductList,
  StorefrontProduct,
  SubmitOrderPayload,
  SubmittedOrder,
} from "./types.js";

export interface StorefrontClientOptions {
  /** Base URL of your IMS API, e.g. "https://api.yourims.com" */
  baseUrl: string;
  /** Channel ID (UUID) for your headless storefront channel */
  channelId: string;
  /** Optional customer JWT — set after OTP login */
  customerToken?: string;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const err = (await res.json()) as ApiError;
      if (err.detail) detail = err.detail;
    } catch {
      /* ignore parse error */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export class StorefrontClient {
  private readonly base: string;
  private readonly channelId: string;
  private customerToken: string | undefined;

  constructor(options: StorefrontClientOptions) {
    this.base = options.baseUrl.replace(/\/$/, "");
    this.channelId = options.channelId;
    this.customerToken = options.customerToken;
  }

  /** Update the customer JWT after successful OTP verification */
  setCustomerToken(token: string): void {
    this.customerToken = token;
  }

  private headers(extra?: Record<string, string>): Record<string, string> {
    const h: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Channel-Id": this.channelId,
      ...extra,
    };
    if (this.customerToken) {
      h["Authorization"] = `Bearer ${this.customerToken}`;
    }
    return h;
  }

  private url(path: string): string {
    return `${this.base}/v1/storefront${path}`;
  }

  // ── Catalog ──────────────────────────────────────────────────────────────

  async listProducts(params?: {
    q?: string;
    status?: string;
    page?: number;
    per_page?: number;
  }): Promise<ProductList> {
    const qs = new URLSearchParams();
    if (params?.q) qs.set("q", params.q);
    if (params?.status) qs.set("status", params.status);
    if (params?.page !== undefined) qs.set("page", String(params.page));
    if (params?.per_page !== undefined) qs.set("per_page", String(params.per_page));
    const res = await fetch(
      `${this.url("/products")}${qs.toString() ? `?${qs}` : ""}`,
      { headers: this.headers() }
    );
    return handleResponse<ProductList>(res);
  }

  async getProduct(slugOrId: string): Promise<StorefrontProduct> {
    const res = await fetch(this.url(`/products/${slugOrId}`), {
      headers: this.headers(),
    });
    return handleResponse<StorefrontProduct>(res);
  }

  // ── Cart ─────────────────────────────────────────────────────────────────

  async createCart(): Promise<Cart> {
    const res = await fetch(this.url("/cart"), {
      method: "POST",
      headers: this.headers(),
    });
    return handleResponse<Cart>(res);
  }

  async getCart(cartToken: string): Promise<Cart> {
    const res = await fetch(this.url(`/cart/${cartToken}`), {
      headers: this.headers(),
    });
    return handleResponse<Cart>(res);
  }

  async addToCart(cartToken: string, productId: string, quantity: number): Promise<Cart> {
    const res = await fetch(this.url(`/cart/${cartToken}/items`), {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ product_id: productId, quantity }),
    });
    return handleResponse<Cart>(res);
  }

  async removeFromCart(cartToken: string, itemId: string): Promise<Cart> {
    const res = await fetch(this.url(`/cart/${cartToken}/items/${itemId}`), {
      method: "DELETE",
      headers: this.headers(),
    });
    return handleResponse<Cart>(res);
  }

  async getCartSummary(cartToken: string): Promise<CartSummary> {
    const res = await fetch(this.url(`/cart/${cartToken}/summary`), {
      headers: this.headers(),
    });
    return handleResponse<CartSummary>(res);
  }

  async applyDiscount(cartToken: string, code: string): Promise<DiscountApplyResult> {
    const res = await fetch(this.url(`/cart/${cartToken}/discount`), {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ code }),
    });
    return handleResponse<DiscountApplyResult>(res);
  }

  // ── Hosted checkout ───────────────────────────────────────────────────────

  async createCheckoutSession(cartToken: string): Promise<CheckoutSession> {
    const res = await fetch(this.url("/checkout/session"), {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ cart_token: cartToken }),
    });
    return handleResponse<CheckoutSession>(res);
  }

  async createPaymentIntent(
    sessionToken: string,
    customerEmail: string,
    shippingAddress?: Record<string, string>
  ): Promise<PaymentIntentResult> {
    const res = await fetch(`${this.base}/v1/checkout/${sessionToken}/payment-intent`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({
        customer_email: customerEmail,
        shipping_address: shippingAddress ?? {},
      }),
    });
    return handleResponse<PaymentIntentResult>(res);
  }

  async completeCheckout(
    sessionToken: string,
    payload: {
      customer_email?: string;
      payment_intent_id?: string;
      razorpay_order_id?: string;
      razorpay_payment_id?: string;
      razorpay_signature?: string;
    }
  ): Promise<CheckoutCompleteResult> {
    const res = await fetch(`${this.base}/v1/checkout/${sessionToken}/complete`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(payload),
    });
    return handleResponse<CheckoutCompleteResult>(res);
  }

  // ── Direct order submit ───────────────────────────────────────────────────

  async submitOrder(payload: SubmitOrderPayload): Promise<SubmittedOrder> {
    const res = await fetch(this.url("/orders"), {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(payload),
    });
    return handleResponse<SubmittedOrder>(res);
  }

  // ── Customer auth (OTP) ───────────────────────────────────────────────────

  async requestOTP(email: string): Promise<OTPRequestResult> {
    const res = await fetch(this.url("/auth/otp/request"), {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ email }),
    });
    return handleResponse<OTPRequestResult>(res);
  }

  async verifyOTP(email: string, code: string): Promise<OTPVerifyResult> {
    const res = await fetch(this.url("/auth/otp/verify"), {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ email, code }),
    });
    const result = await handleResponse<OTPVerifyResult>(res);
    this.setCustomerToken(result.access_token);
    return result;
  }

  // ── Customer auth (magic link) ────────────────────────────────────────────

  async requestMagicLink(email: string, redirectUrl: string): Promise<MagicLinkRequestResponse> {
    const res = await fetch(this.url("/auth/magic-link/request"), {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ email, redirect_url: redirectUrl }),
    });
    return handleResponse<MagicLinkRequestResponse>(res);
  }

  async verifyMagicLink(token: string): Promise<MagicLinkVerifyResponse> {
    const res = await fetch(this.url("/auth/magic-link/verify"), {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ token }),
    });
    const result = await handleResponse<MagicLinkVerifyResponse>(res);
    this.setCustomerToken(result.access_token);
    return result;
  }

  // ── Customer portal ───────────────────────────────────────────────────────

  async getCustomerProfile(): Promise<CustomerProfile> {
    const res = await fetch(this.url("/customers/me"), {
      headers: this.headers(),
    });
    return handleResponse<CustomerProfile>(res);
  }

  async getOrderHistory(params?: {
    limit?: number;
    offset?: number;
  }): Promise<CustomerOrder[]> {
    const qs = new URLSearchParams();
    if (params?.limit !== undefined) qs.set("limit", String(params.limit));
    if (params?.offset !== undefined) qs.set("offset", String(params.offset));
    const res = await fetch(
      `${this.url("/customers/me/orders")}${qs.toString() ? `?${qs}` : ""}`,
      { headers: this.headers() }
    );
    return handleResponse<CustomerOrder[]>(res);
  }
}
