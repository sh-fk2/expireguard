/* ExpireGuard フロント（素の JS。ビルド不要）。
 * 認証は Cognito（auth.js）。IdToken を Authorization ヘッダーで API に送る。
 * 設定は config.js の window.EXPIREGUARD_CONFIG（apiBaseUrl / userPoolClientId / region）で渡す。 */
(function () {
  "use strict";

  var CONFIG = window.EXPIREGUARD_CONFIG || {};
  var API_BASE = (CONFIG.apiBaseUrl || "").replace(/\/$/, "");
  var LANG_KEY = "expireguard.lang";
  var MAX_IMAGE_BYTES = 3750000; // サーバー側（api /uploads の maxBytes）と同じ上限
  var IMAGE_TYPES = ["image/png", "image/jpeg"];
  var MANUAL_SERVICES = ["楽天ポイント", "dポイント", "PayPayポイント", "ANAマイル", "JALマイル", "その他"];

  var I18N = {
    en: {
      nav_dashboard: "Dashboard", nav_screenshot: "Add screenshot", nav_review: "Review", nav_manual: "Add manually",
      stat_risk_label: "Expiring in the next 30 days",
      stat_charge_label: "Auto-charge this month", stat_saved_label: "Saved so far", stat_saved_sub: "Used or cancelled in time",
      list_title: "Coming up", add_btn: "Add", test_notify: "Send test notification",
      type_points: "Points", type_sub_badge: "Subscription", limited: "Limited-time",
      expires: "Expires", renews: "Renews",
      in_days: function (n) { return n === 1 ? "in 1 day" : "in " + n + " days"; },
      today: "today", expired: "Expired", no_expiry: "No expiry",
      act_used: "Used", act_cancelled: "Cancelled", act_delete: "Delete",
      confirm_delete: "Delete this item?",
      list_empty: "Nothing coming up. Add a screenshot or enter an item manually.",
      risk_sub: function (n) {
        if (n === 0) return "Nothing needs attention";
        return n === 1 ? "1 item needs attention" : n + " items need attention";
      },
      charge_none: "No charges scheduled this month",
      charge_sub: function (n) { return n === 1 ? "1 renewal this month" : n + " renewals this month"; },
      up_title: "Add a screenshot",
      up_sub: "A balance screen or a subscription list. We read the amounts and dates for you.",
      step_upload: "Upload", step_review: "Review", step_done: "Done",
      dz_title: "Drop your screenshot here", dz_sub: "PNG or JPG, up to 3.5 MB",
      dz_choose: "Choose file", dz_manual: "Enter manually instead",
      file_ready: "Ready", badge_uploading: "Uploading…", badge_reading: "Reading…",
      reading_title: "Reading your screenshot…", reading_sub: "Finding amounts and expiry dates.",
      extract_btn: "Extract", cancel: "Cancel", back: "Back",
      rv_title: "Review extracted items", rv_sub: "Check the values before saving. Anything can be edited.",
      items_found: function (n) { return n === 1 ? "1 item" : n + " items"; },
      extracted: "Extracted",
      rv_empty_title: "Nothing to review", rv_empty_sub: "Add a screenshot and the items we find will appear here.",
      rv_empty_btn: "Add a screenshot",
      f_service: "Service", f_kind: "Kind", f_type: "Type", f_amount: "Amount", f_expiry: "Expiry date",
      f_renewal: "Renewal date", f_cycle: "Billing cycle",
      cycle_monthly: "Monthly", cycle_yearly: "Yearly",
      type_regular: "Regular points", type_limited: "Limited-time points", type_sub: "Subscription",
      save_items: function (n) { return "Save " + n + (n === 1 ? " item" : " items"); },
      mn_title: "Add manually", mn_sub: "Points, coupons, or a subscription renewal.",
      kind_points: "Points", kind_sub: "Subscription",
      f_ptype: "Point type", type_regular_short: "Regular", type_limited_short: "Limited-time",
      service_ph: "e.g. Rakuten Points", amount_ph: "e.g. 1,240",
      f_quick: "Quick set", quick_eom: "End of this month", quick_next: "End of next month",
      add_item: "Add item",
      sign_out: "Sign out",
      login_title: "Sign in", login_sub: "Use the account your administrator created for you.",
      login_email: "Email", login_password: "Password", login_btn: "Sign in",
      np_title: "Set a new password", np_sub: "This is your first sign-in. Choose a new password to continue.",
      np_new: "New password", np_confirm: "Confirm new password", np_btn: "Set password and sign in",
      np_hint: "At least 12 characters, with upper and lower case letters, a number and a symbol.",
      auth_err_credentials: "The email or password is incorrect.",
      auth_err_policy: "The new password does not meet the requirements.",
      auth_err_mismatch: "The two passwords do not match.",
      auth_err_required: "Please enter your email and password.",
      auth_err_throttle: "Too many attempts. Please wait a moment and try again.",
      auth_err_admin: "This account needs an administrator's help. Please contact them.",
      auth_err_network: "Could not reach the sign-in service. Check your connection and try again.",
      auth_err_challenge_expired: "The sign-in session timed out. Please sign in again.",
      auth_err_no_config: "Sign-in is not configured (config.js).",
      auth_session_expired: "Your session has expired. Please sign in again.",
      err_generic: "Something went wrong. Please try again.",
      err_not_found: "The item could not be found. It may have been deleted, so please refresh the list.",
      err_invalid: "The input is not valid. Please check it and try again.",
      err_conflict: "This item can no longer be changed.",
      err_throttle: "Too many requests. Please wait a moment and try again.",
      err_no_api: "The API address is not configured (config.js).",
      err_type: "Please choose a PNG or JPG image.",
      err_size: "The image is too large (up to 3.5 MB).",
      err_required: "Please fill in the highlighted fields.",
      info_nothing_read: "We couldn't read this screenshot. Please enter the details below.",
      info_extract_failed: "Reading the screenshot failed. Please enter the details below.",
      ok_saved: "Saved.",
      ok_test_sent: "Test notification sent.",
      ok_test_sample: "No active items yet, so a sample notification was sent.",
      money: function (n) { return "¥" + n.toLocaleString("en-US"); },
      moneyUnit: function (n) { return "¥" + n.toLocaleString("en-US"); },
      dateFmt: function (iso) {
        var p = iso.split("-");
        return new Date(+p[0], +p[1] - 1, +p[2]).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
      }
    },
    ja: {
      nav_dashboard: "ダッシュボード", nav_screenshot: "スクショ登録", nav_review: "確認", nav_manual: "手入力",
      stat_risk_label: "今後30日で期限切れ",
      stat_charge_label: "今月の自動課金予定", stat_saved_label: "守れた金額", stat_saved_sub: "期限内に使った・解約した分",
      list_title: "期限が近い順", add_btn: "追加", test_notify: "テスト通知を送る",
      type_points: "ポイント", type_sub_badge: "サブスク", limited: "期間限定",
      expires: "期限", renews: "次回更新",
      in_days: function (n) { return "あと" + n + "日"; },
      today: "今日", expired: "期限切れ", no_expiry: "期限なし",
      act_used: "使った", act_cancelled: "解約した", act_delete: "削除",
      confirm_delete: "このアイテムを削除しますか？",
      list_empty: "期限が近いものはありません。スクショ登録か手入力で追加できます。",
      risk_sub: function (n) { return n === 0 ? "対応が必要なものはありません" : "対応が必要なのは" + n + "件"; },
      charge_none: "今月の課金予定はありません",
      charge_sub: function (n) { return "今月の更新は" + n + "件"; },
      up_title: "スクリーンショット登録",
      up_sub: "残高画面やサブスク一覧のスクショから、金額と日付を読み取ります。",
      step_upload: "アップロード", step_review: "確認", step_done: "完了",
      dz_title: "スクショをここにドロップ", dz_sub: "PNG / JPG、3.5 MBまで",
      dz_choose: "ファイルを選ぶ", dz_manual: "手入力する",
      file_ready: "準備完了", badge_uploading: "アップロード中", badge_reading: "読み取り中",
      reading_title: "スクショを読み取り中…", reading_sub: "金額と期限を探しています。",
      extract_btn: "読み取る", cancel: "キャンセル", back: "戻る",
      rv_title: "読み取り結果の確認", rv_sub: "保存前に値を確認してください。すべて修正できます。",
      items_found: function (n) { return n + "件"; },
      extracted: "読み取り済み",
      rv_empty_title: "確認する項目はありません", rv_empty_sub: "スクショを登録すると、読み取った項目がここに表示されます。",
      rv_empty_btn: "スクショを登録する",
      f_service: "サービス名", f_kind: "種類", f_type: "種別", f_amount: "ポイント数・金額", f_expiry: "有効期限",
      f_renewal: "次回更新日", f_cycle: "課金周期",
      cycle_monthly: "月次", cycle_yearly: "年次",
      type_regular: "通常ポイント", type_limited: "期間限定ポイント", type_sub: "サブスクリプション",
      save_items: function (n) { return n + "件を保存"; },
      mn_title: "手入力で追加", mn_sub: "ポイント、クーポン、サブスクの更新日など。",
      kind_points: "ポイント", kind_sub: "サブスクリプション",
      f_ptype: "ポイント種別", type_regular_short: "通常", type_limited_short: "期間限定",
      service_ph: "例：楽天ポイント", amount_ph: "例：1,240",
      f_quick: "かんたん入力", quick_eom: "今月末", quick_next: "来月末",
      add_item: "追加する",
      sign_out: "ログアウト",
      login_title: "ログイン", login_sub: "管理者が作成したアカウントでログインしてください。",
      login_email: "メールアドレス", login_password: "パスワード", login_btn: "ログイン",
      np_title: "新しいパスワードの設定", np_sub: "初回ログインです。新しいパスワードを設定してください。",
      np_new: "新しいパスワード", np_confirm: "新しいパスワード（確認）", np_btn: "パスワードを設定してログイン",
      np_hint: "12文字以上で、英大文字・英小文字・数字・記号を含めてください。",
      auth_err_credentials: "メールアドレスまたはパスワードが正しくありません。",
      auth_err_policy: "新しいパスワードが要件を満たしていません。",
      auth_err_mismatch: "2つのパスワードが一致しません。",
      auth_err_required: "メールアドレスとパスワードを入力してください。",
      auth_err_throttle: "試行回数が多すぎます。しばらく待ってからお試しください。",
      auth_err_admin: "このアカウントは管理者の対応が必要です。管理者に連絡してください。",
      auth_err_network: "ログインサービスに接続できません。通信環境を確認して再度お試しください。",
      auth_err_challenge_expired: "ログインの有効時間が切れました。もう一度ログインしてください。",
      auth_err_no_config: "ログインの設定が未設定です（config.js）。",
      auth_session_expired: "セッションの有効期限が切れました。もう一度ログインしてください。",
      err_generic: "問題が発生しました。もう一度お試しください。",
      err_not_found: "アイテムが見つかりません。削除済みの可能性があるので、一覧を更新してください。",
      err_invalid: "入力が正しくありません。内容を確認してもう一度お試しください。",
      err_conflict: "このアイテムは、すでに変更できない状態です。",
      err_throttle: "リクエストが多すぎます。しばらく待ってからお試しください。",
      err_no_api: "API のアドレスが未設定です（config.js）。",
      err_type: "PNG または JPG の画像を選んでください。",
      err_size: "画像が大きすぎます（3.5 MBまで）。",
      err_required: "色の付いた項目を入力してください。",
      info_nothing_read: "スクショから読み取れませんでした。下のフォームに入力してください。",
      info_extract_failed: "読み取りに失敗しました。下のフォームに入力してください。",
      ok_saved: "保存しました。",
      ok_test_sent: "テスト通知を送信しました。",
      ok_test_sample: "有効なアイテムがないため、サンプルの通知を送信しました。",
      money: function (n) { return n.toLocaleString("ja-JP") + "円"; },
      moneyUnit: function (n) { return n.toLocaleString("ja-JP") + "円分"; },
      dateFmt: function (iso) {
        var p = iso.split("-");
        return p[0] + "年" + (+p[1]) + "月" + (+p[2]) + "日";
      }
    }
  };

  var state = { lang: "en", summary: null, pending: [], sourceKey: null, busy: false };
  var loginMessage = null; // { key, kind }: 言語切替でも再描画できるようキーで保持する
  var challenge = null; // NEW_PASSWORD_REQUIRED の続行に使う（メモリのみ。保存しない）

  /* ---------- 認証（auth.js） ---------- */
  var auth = null;
  try {
    auth = window.ExpireGuardAuth.createAuth({
      clientId: CONFIG.userPoolClientId,
      region: CONFIG.region,
      fetchFn: function (url, opts) { return window.fetch(url, opts); },
      storage: window.sessionStorage
    });
  } catch (e) {
    auth = null; // 設定不足。ログイン画面でエラーを表示する
  }

  /* ---------- ユーティリティ ---------- */
  function $(id) { return document.getElementById(id); }
  function t() { return I18N[state.lang]; }
  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function parseAmount(str) {
    var digits = String(str == null ? "" : str).replace(/[^0-9]/g, "");
    return digits ? parseInt(digits, 10) : 0;
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function isoDate(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function dayClass(n) { return n <= 7 ? "red" : (n <= 30 ? "amber" : ""); }
  function segValue(id, attr) {
    var b = document.querySelector("#" + id + " button[aria-pressed='true']");
    return b ? b.getAttribute(attr) : null;
  }
  function setSeg(id, attr, value) {
    document.querySelectorAll("#" + id + " button").forEach(function (b) {
      b.setAttribute("aria-pressed", b.getAttribute(attr) === value ? "true" : "false");
    });
  }

  function showBanner(message, kind) {
    var el = $("banner");
    el.textContent = message;
    el.className = "banner " + (kind || "error");
    el.hidden = false;
  }
  function hideBanner() { $("banner").hidden = true; }

  /* ---------- API ---------- */
  function authRequiredError() {
    var err = new Error(t().auth_session_expired);
    err.authRequired = true;
    return err;
  }

  /* セッション切れ: 保存を消してログイン画面へ戻す */
  function expireSession() {
    showLogin("auth_session_expired", "info");
    return Promise.reject(authRequiredError());
  }

  /* サーバーの message は日本語固定なので表示に使わず、ステータスから現在の言語の文言を選ぶ */
  function messageForStatus(status) {
    var tx = t();
    if (status === 400) return tx.err_invalid;
    if (status === 404) return tx.err_not_found;
    if (status === 409) return tx.err_conflict;
    if (status === 429) return tx.err_throttle;
    return tx.err_generic;
  }

  function request(method, path, body, isRetry) {
    return auth.getIdToken({ forceRefresh: isRetry }).then(function (token) {
      if (!token) return expireSession();
      var opts = { method: method, headers: { Authorization: "Bearer " + token } };
      if (body !== undefined) {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
      }
      return fetch(API_BASE + path, opts).then(function (res) {
        // 401 は IdToken を更新して1回だけ再試行し、それでも 401 ならログインへ戻す
        if (res.status === 401) return isRetry ? expireSession() : request(method, path, body, true);
        if (res.status === 204) return null;
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok) {
            var err = new Error(messageForStatus(res.status));
            err.status = res.status;
            err.fields = data.fields || [];
            throw err;
          }
          return data;
        });
      });
    }, function (authErr) {
      throw new Error(authErr && authErr.code === "NetworkError" ? t().auth_err_network : t().err_generic);
    });
  }

  function api(method, path, body) {
    if (!API_BASE) return Promise.reject(new Error(t().err_no_api));
    if (!auth) return expireSession();
    return request(method, path, body, false);
  }

  function reportError(err) {
    if (err && err.authRequired) return; // ログイン画面へ戻っており、メッセージはそちらに表示する
    showBanner(err && err.message ? err.message : t().err_generic, "error");
  }

  /* ---------- ダッシュボード ---------- */
  function iconFor(kind) {
    if (kind === "subscription") {
      return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>';
    }
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v12"/><path d="M15.5 9.5c-.7-1-2-1.5-3.5-1.5-2 0-3.5 1.1-3.5 2.5 0 3.6 7 2.2 7 4.5 0 1.4-1.5 2.5-3.5 2.5-1.5 0-2.8-.6-3.5-1.5"/></svg>';
  }

  function renderList() {
    var tx = t();
    var box = $("item-list");
    var items = state.summary ? state.summary.items : [];
    if (!items.length) {
      box.innerHTML = '<div class="list-empty">' + esc(tx.list_empty) + "</div>";
      return;
    }
    box.innerHTML = items.map(function (it) {
      var isSub = it.kind === "subscription";
      var amount = isSub ? tx.money(it.amount) : it.points.toLocaleString("en-US") + " pt";
      var n = it.daysLeft;
      var dayText = n < 0 ? tx.expired : (n === 0 ? tx.today : tx.in_days(n));
      var days = '<div class="item-days ' + (n < 0 ? "red" : dayClass(n)) + '">' + esc(dayText) + "</div>";
      var meta = (isSub ? tx.renews : tx.expires) + " · " + tx.dateFmt(it.expiryDate);
      var limited = (!isSub && it.isLimited) ? ' <span style="color:var(--mid);font-weight:400">· ' + esc(tx.limited) + "</span>" : "";
      var id = esc(it.itemId);
      return '<div class="item-row">'
        + '<div class="item-icon">' + iconFor(it.kind) + "</div>"
        + '<div class="item-main"><div class="item-name">' + esc(it.service) + limited
        + ' <span class="badge badge-soft">' + esc(isSub ? tx.type_sub_badge : tx.type_points) + "</span></div>"
        + '<div class="item-meta">' + esc(meta) + "</div></div>"
        + '<div class="item-right"><div class="item-amount tnum">' + esc(amount) + "</div>" + days + "</div>"
        + '<div class="item-actions">'
        + '<button type="button" class="row-action" data-resolve="' + id + '">' + esc(isSub ? tx.act_cancelled : tx.act_used) + "</button>"
        + '<button type="button" class="row-action row-delete" data-delete="' + id + '">' + esc(tx.act_delete) + "</button>"
        + "</div></div>";
    }).join("");
  }

  function renderStats() {
    var tx = t();
    var s = state.summary || { atRiskAmount: 0, atRiskCount: 0, upcomingCharges: { amount: 0, count: 0 }, savedAmount: 0 };
    $("risk-amount").textContent = tx.moneyUnit(s.atRiskAmount);
    $("risk-sub").textContent = tx.risk_sub(s.atRiskCount);
    $("charge-amount").textContent = tx.money(s.upcomingCharges.amount);
    $("charge-sub").textContent = s.upcomingCharges.count ? tx.charge_sub(s.upcomingCharges.count) : tx.charge_none;
    $("saved-amount").textContent = tx.moneyUnit(s.savedAmount);
  }

  function loadSummary() {
    return api("GET", "/summary").then(function (data) {
      state.summary = data;
      renderStats();
      renderList();
    }).catch(reportError);
  }

  $("item-list").addEventListener("click", function (e) {
    var resolve = e.target.closest("[data-resolve]");
    var del = e.target.closest("[data-delete]");
    if (resolve) {
      var item = findItem(resolve.getAttribute("data-resolve"));
      var status = item && item.kind === "subscription" ? "cancelled" : "used";
      api("PATCH", "/items/" + encodeURIComponent(resolve.getAttribute("data-resolve")), { status: status })
        .then(loadSummary).catch(reportError);
    } else if (del && window.confirm(t().confirm_delete)) {
      api("DELETE", "/items/" + encodeURIComponent(del.getAttribute("data-delete")))
        .catch(function (err) {
          // すでに削除済み（404）は目的が達成されているので、エラーにせず一覧を更新する
          if (err && err.status === 404) return null;
          throw err;
        })
        .then(loadSummary).catch(reportError);
    }
  });

  function findItem(id) {
    var items = state.summary ? state.summary.items : [];
    for (var i = 0; i < items.length; i++) { if (items[i].itemId === id) return items[i]; }
    return null;
  }

  $("test-notify-btn").addEventListener("click", function () {
    hideBanner();
    api("POST", "/notify/test").then(function (res) {
      showBanner(res.sample ? t().ok_test_sample : t().ok_test_sent, "ok");
    }).catch(reportError);
  });

  /* ---------- スクショ登録 ---------- */
  function setBusy(isBusy, label) {
    state.busy = isBusy;
    $("reading-panel").classList.toggle("on", isBusy);
    $("dz-choose-btn").toggleAttribute("disabled", isBusy);
    $("extract-btn").toggleAttribute("disabled", isBusy);
    $("shot-file-badge").textContent = isBusy ? label : t().file_ready;
  }

  function blankLot(kind) {
    return { draftId: null, kind: kind || "points", service: "", amount: "", expiryDate: "", isLimited: false, cycle: "monthly", extracted: {} };
  }

  function lotFromDraft(d) {
    var isSub = d.kind === "subscription";
    return {
      draftId: d.itemId,
      kind: d.kind,
      service: d.service || "",
      amount: (isSub ? d.amount : d.points) || "",
      expiryDate: d.expiryDate || "",
      isLimited: !!d.isLimited,
      cycle: d.cycle || "monthly",
      extracted: { service: !!d.service, amount: !!(isSub ? d.amount : d.points), expiryDate: !!d.expiryDate, cycle: !!d.cycle }
    };
  }

  function uploadFile(file) {
    return api("POST", "/uploads", { contentType: file.type }).then(function (up) {
      var form = new FormData();
      Object.keys(up.fields).forEach(function (k) { form.append(k, up.fields[k]); });
      form.append("file", file); // file は最後のフィールドにする（S3 署名付き POST の仕様）
      return fetch(up.url, { method: "POST", body: form }).then(function (res) {
        if (!res.ok) throw new Error(t().err_generic);
        return up.key;
      });
    });
  }

  function handleFile(file) {
    if (state.busy || !file) return;
    hideBanner();
    if (IMAGE_TYPES.indexOf(file.type) < 0) { showBanner(t().err_type); return; }
    if (file.size > MAX_IMAGE_BYTES) { showBanner(t().err_size); return; }
    $("file-row").style.display = "flex";
    $("shot-file-name").textContent = file.name;
    $("rv-file-name").textContent = file.name;
    $("shot-file-meta").textContent = (file.size / 1048576).toFixed(1) + " MB";
    setBusy(true, t().badge_uploading);

    uploadFile(file).then(function (key) {
      state.sourceKey = key;
      $("shot-file-badge").textContent = t().badge_reading;
      // 抽出に失敗しても、確認画面を空フォームで開いて手入力に落とす
      return api("POST", "/extract", { key: key }).then(function (res) {
        if (res.items && res.items.length) {
          state.pending = res.items.map(lotFromDraft);
        } else {
          state.pending = [blankLot()];
          showBanner(t().info_nothing_read, "info");
        }
      }).catch(function (err) {
        if (err && err.authRequired) throw err;
        state.pending = [blankLot()];
        showBanner(t().info_extract_failed, "info");
      });
    }).then(function () {
      setBusy(false);
      renderReview();
      showScreen("review", true);
    }).catch(function (err) {
      setBusy(false);
      reportError(err);
    });
  }

  $("dz-choose-btn").addEventListener("click", function () { $("file-input").click(); });
  $("file-input").addEventListener("change", function () {
    var f = $("file-input").files && $("file-input").files[0];
    $("file-input").value = "";
    handleFile(f);
  });
  $("extract-btn").addEventListener("click", function () { $("file-input").click(); });
  var dropzone = document.querySelector(".dropzone");
  ["dragover", "dragenter"].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) { e.preventDefault(); });
  });
  dropzone.addEventListener("drop", function (e) {
    e.preventDefault();
    handleFile(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]);
  });

  /* ---------- 確認画面 ---------- */
  function lotCardHtml(lot, i) {
    var tx = t();
    var isSub = lot.kind === "subscription";
    var ex = function (f) { return lot.extracted[f] ? " extracted" : ""; };
    var sel = function (cond) { return cond ? " selected" : ""; };
    var typeVal = lot.kind === "subscription" ? "subscription" : (lot.isLimited ? "limited" : "regular");
    var cycleField = isSub
      ? '<div class="field"><label>' + esc(tx.f_cycle) + '</label><select class="lot-cycle' + ex("cycle") + '">'
        + '<option value="monthly"' + sel(lot.cycle === "monthly") + ">" + esc(tx.cycle_monthly) + "</option>"
        + '<option value="yearly"' + sel(lot.cycle === "yearly") + ">" + esc(tx.cycle_yearly) + "</option></select></div>"
      : "";
    return '<div class="card lot-card" data-lot="' + i + '">'
      + '<div class="lot-head"><div class="lot-title">' + esc(lot.service || "—")
      + (lot.draftId ? ' <span class="badge badge-solid">' + esc(tx.extracted) + "</span>" : "") + "</div></div>"
      + '<div class="form-grid">'
      + '<div class="field"><label>' + esc(tx.f_service) + '</label><input type="text" class="lot-service' + ex("service") + '" value="' + esc(lot.service) + '" /></div>'
      + '<div class="field"><label>' + esc(tx.f_type) + '</label><select class="lot-type">'
      + '<option value="regular"' + sel(typeVal === "regular") + ">" + esc(tx.type_regular) + "</option>"
      + '<option value="limited"' + sel(typeVal === "limited") + ">" + esc(tx.type_limited) + "</option>"
      + '<option value="subscription"' + sel(typeVal === "subscription") + ">" + esc(tx.type_sub) + "</option></select></div>"
      + '<div class="field"><label>' + esc(tx.f_amount) + '</label><input type="text" inputmode="numeric" class="tnum lot-amount' + ex("amount") + '" value="' + esc(lot.amount) + '" /></div>'
      + '<div class="field"><label>' + esc(isSub ? tx.f_renewal : tx.f_expiry) + '</label><input type="date" class="tnum lot-expiry' + ex("expiryDate") + '" value="' + esc(lot.expiryDate) + '" /></div>'
      + cycleField
      + "</div></div>";
  }

  /* 入力中の値を state.pending に反映する（種別切替や言語切替での再描画で消えないように） */
  function syncPending() {
    document.querySelectorAll("#review-lots .lot-card").forEach(function (card) {
      var lot = state.pending[+card.getAttribute("data-lot")];
      if (!lot) return;
      var type = card.querySelector(".lot-type").value;
      lot.kind = type === "subscription" ? "subscription" : "points";
      lot.isLimited = type === "limited";
      lot.service = card.querySelector(".lot-service").value;
      lot.amount = card.querySelector(".lot-amount").value;
      lot.expiryDate = card.querySelector(".lot-expiry").value;
      var cyc = card.querySelector(".lot-cycle");
      if (cyc) lot.cycle = cyc.value;
    });
  }

  function renderReview() {
    var tx = t();
    var lots = state.pending;
    $("rv-found").textContent = tx.items_found(lots.length);
    $("review-empty").style.display = lots.length ? "none" : "block";
    $("review-actions").style.display = lots.length ? "flex" : "none";
    $("review-lots").innerHTML = lots.map(lotCardHtml).join("");
    $("save-review-btn").textContent = tx.save_items(lots.length);
  }

  $("review-lots").addEventListener("change", function (e) {
    if (e.target.classList.contains("lot-type")) { syncPending(); renderReview(); }
  });
  $("review-lots").addEventListener("input", function (e) {
    // 利用者が直した項目は「読み取り済み」の色を外す
    e.target.classList.remove("extracted", "invalid");
  });

  function lotPayload(card, lot) {
    var type = card.querySelector(".lot-type").value;
    var amount = parseAmount(card.querySelector(".lot-amount").value);
    var payload = {
      service: card.querySelector(".lot-service").value.trim(),
      expiryDate: card.querySelector(".lot-expiry").value
    };
    if (lot.draftId) payload.draftId = lot.draftId;
    if (type === "subscription") {
      payload.kind = "subscription";
      payload.amount = amount;
      payload.cycle = card.querySelector(".lot-cycle") ? card.querySelector(".lot-cycle").value : "monthly";
    } else {
      payload.kind = "points";
      payload.points = amount;
      payload.isLimited = type === "limited";
    }
    return payload;
  }

  function markInvalid(card, fields) {
    var map = { service: ".lot-service", expiryDate: ".lot-expiry", points: ".lot-amount", amount: ".lot-amount", cycle: ".lot-cycle" };
    fields.forEach(function (f) {
      var el = map[f] && card.querySelector(map[f]);
      if (el) el.classList.add("invalid");
    });
  }

  $("save-review-btn").addEventListener("click", function () {
    hideBanner();
    syncPending();
    var cards = Array.prototype.slice.call(document.querySelectorAll("#review-lots .lot-card"));
    var chain = Promise.resolve(true);
    cards.forEach(function (card, i) {
      chain = chain.then(function (allOk) {
        var lot = state.pending[i];
        if (!lot) return allOk;
        return api("POST", "/items", lotPayload(card, lot)).then(function () {
          lot.saved = true;
          return allOk;
        }).catch(function (err) {
          markInvalid(card, err.fields || []);
          showBanner(err.fields && err.fields.length ? t().err_required : err.message);
          return false;
        });
      });
    });
    chain.then(function (allOk) {
      // 保存済みのロットは取り除き、失敗したものだけを確認画面に残す
      state.pending = state.pending.filter(function (l) { return !l.saved; });
      renderReview();
      if (allOk) {
        showBanner(t().ok_saved, "ok");
        loadSummary();
        showScreen("dashboard", true);
      }
    });
  });

  /* ---------- 手入力 ---------- */
  function renderManualChips() {
    $("manual-chips").innerHTML = MANUAL_SERVICES.map(function (s) {
      return '<button type="button" class="chip" aria-pressed="false">' + esc(s) + "</button>";
    }).join("");
  }
  $("manual-chips").addEventListener("click", function (e) {
    var b = e.target.closest(".chip");
    if (!b) return;
    $("manual-chips").querySelectorAll(".chip").forEach(function (c) { c.setAttribute("aria-pressed", "false"); });
    b.setAttribute("aria-pressed", "true");
    var name = b.textContent.trim();
    $("mn-service").value = name === "その他" ? "" : name;
    if (name === "その他") $("mn-service").focus();
  });

  document.querySelectorAll("[data-quick]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var now = new Date();
      var offset = btn.getAttribute("data-quick") === "eom" ? 1 : 2;
      $("mn-date").value = isoDate(new Date(now.getFullYear(), now.getMonth() + offset, 0));
    });
  });

  function updateKindFields() {
    var isSub = segValue("kind-seg", "data-kind") === "subscription";
    $("ptype-field").style.display = isSub ? "none" : "flex";
    $("cycle-field").style.display = isSub ? "flex" : "none";
    $("mn-date-label").textContent = isSub ? t().f_renewal : t().f_expiry;
  }
  $("kind-seg").addEventListener("click", updateKindFields);

  $("mn-add").addEventListener("click", function () {
    hideBanner();
    var isSub = segValue("kind-seg", "data-kind") === "subscription";
    var amount = parseAmount($("mn-amount").value);
    var payload = {
      kind: isSub ? "subscription" : "points",
      service: $("mn-service").value.trim(),
      expiryDate: $("mn-date").value
    };
    if (isSub) {
      payload.amount = amount;
      payload.cycle = segValue("cycle-seg", "data-cycle") || "monthly";
    } else {
      payload.points = amount;
      payload.isLimited = segValue("ptype-seg", "data-ptype") === "limited";
    }
    api("POST", "/items", payload).then(function () {
      $("mn-service").value = "";
      $("mn-amount").value = "";
      $("mn-date").value = "";
      showBanner(t().ok_saved, "ok");
      loadSummary();
      showScreen("dashboard", true);
    }).catch(reportError);
  });

  document.querySelectorAll(".segmented").forEach(function (seg) {
    seg.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      seg.querySelectorAll("button").forEach(function (x) { x.setAttribute("aria-pressed", "false"); });
      b.setAttribute("aria-pressed", "true");
    });
  });

  /* ---------- ログイン ---------- */
  function setLoginMessage(key, kind) { loginMessage = key ? { key: key, kind: kind || "error" } : null; renderLoginMessage(); }
  function renderLoginMessage() {
    var el = $("login-message");
    if (!loginMessage) { el.hidden = true; el.textContent = ""; return; }
    el.textContent = t()[loginMessage.key] || t().err_generic; // textContent: HTML として解釈しない
    el.className = "banner " + loginMessage.kind;
    el.hidden = false;
  }

  function showLoginStep(step) {
    $("login-form").hidden = step !== "signin";
    $("newpass-form").hidden = step !== "newpass";
  }

  function showLogin(messageKey, kind) {
    if (auth) auth.signOut();
    challenge = null;
    state.summary = null; state.pending = []; state.sourceKey = null;
    $("login-password").value = "";
    $("np-new").value = ""; $("np-confirm").value = "";
    renderStats(); renderList(); renderReview();
    hideBanner();
    $("app-view").hidden = true;
    $("login-view").hidden = false;
    $("logout-btn").hidden = true;
    showLoginStep("signin");
    setLoginMessage(messageKey, kind);
  }

  function showApp() {
    challenge = null;
    $("login-password").value = "";
    $("np-new").value = ""; $("np-confirm").value = "";
    setLoginMessage(null);
    $("login-view").hidden = true;
    $("app-view").hidden = false;
    $("logout-btn").hidden = false;
    showScreen("dashboard");
    loadSummary();
  }

  function authErrorKey(err, inNewPassword) {
    switch (err && err.code) {
      case "NotAuthorizedException":
      case "UserNotFoundException":
        return inNewPassword ? "auth_err_challenge_expired" : "auth_err_credentials";
      case "InvalidPasswordException":
        return "auth_err_policy";
      case "InvalidParameterException":
        return inNewPassword ? "auth_err_policy" : "err_generic";
      case "TooManyRequestsException":
      case "LimitExceededException":
        return "auth_err_throttle";
      case "PasswordResetRequiredException":
      case "UserNotConfirmedException":
      case "UnsupportedChallenge":
        return "auth_err_admin";
      case "NetworkError":
        return "auth_err_network";
      default:
        return "err_generic";
    }
  }

  function setLoginBusy(isBusy) {
    $("login-btn").toggleAttribute("disabled", isBusy);
    $("np-btn").toggleAttribute("disabled", isBusy);
  }

  function handleAuthOutcome(outcome) {
    if (outcome.status === "signed_in") { showApp(); return; }
    challenge = outcome.challenge;
    $("login-password").value = "";
    setLoginMessage(null);
    showLoginStep("newpass");
    $("np-new").focus();
  }

  $("login-form").addEventListener("submit", function (e) {
    e.preventDefault();
    if (!auth) { setLoginMessage("auth_err_no_config", "error"); return; }
    var email = $("login-email").value.trim();
    var password = $("login-password").value;
    if (!email || !password) { setLoginMessage("auth_err_required", "error"); return; }
    setLoginMessage(null);
    setLoginBusy(true);
    auth.signIn(email, password).then(handleAuthOutcome).catch(function (err) {
      $("login-password").value = "";
      setLoginMessage(authErrorKey(err, false), "error");
    }).then(function () { setLoginBusy(false); });
  });

  $("newpass-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var next = $("np-new").value;
    if (!challenge || !next) { setLoginMessage("auth_err_required", "error"); return; }
    if (next !== $("np-confirm").value) { setLoginMessage("auth_err_mismatch", "error"); return; }
    setLoginMessage(null);
    setLoginBusy(true);
    auth.completeNewPassword(challenge, next).then(handleAuthOutcome).catch(function (err) {
      var key = authErrorKey(err, true);
      $("np-new").value = ""; $("np-confirm").value = "";
      if (key === "auth_err_challenge_expired") {
        // チャレンジのセッション切れ: 最初のログインからやり直す
        challenge = null;
        showLoginStep("signin");
      }
      setLoginMessage(key, "error");
    }).then(function () { setLoginBusy(false); });
  });

  $("logout-btn").addEventListener("click", function () { showLogin(null); });

  /* ---------- 言語 ---------- */
  function applyLang(next) {
    state.lang = next;
    try { window.localStorage.setItem(LANG_KEY, next); } catch (e) { /* 保存できなくても動作は継続 */ }
    var tx = t();
    document.documentElement.lang = next;
    $("lang-en").setAttribute("aria-pressed", next === "en" ? "true" : "false");
    $("lang-ja").setAttribute("aria-pressed", next === "ja" ? "true" : "false");
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      var v = tx[el.getAttribute("data-i18n")];
      if (typeof v === "string") el.textContent = v;
    });
    document.querySelectorAll("[data-i18n-ph]").forEach(function (el) {
      var v = tx[el.getAttribute("data-i18n-ph")];
      if (typeof v === "string") el.setAttribute("placeholder", v);
    });
    renderLoginMessage();
    updateKindFields();
    syncPending();
    renderStats();
    renderList();
    renderReview();
  }
  $("lang-en").addEventListener("click", function () { applyLang("en"); });
  $("lang-ja").addEventListener("click", function () { applyLang("ja"); });

  /* ---------- 画面切替 ---------- */
  function showScreen(name, keepBanner) {
    if (!keepBanner) hideBanner();
    document.querySelectorAll("nav.tabs button").forEach(function (b) {
      b.setAttribute("aria-selected", b.getAttribute("data-screen") === name ? "true" : "false");
    });
    document.querySelectorAll("main section.screen").forEach(function (s) {
      s.classList.toggle("active", s.id === "screen-" + name);
    });
    window.scrollTo(0, 0);
  }
  document.querySelectorAll("nav.tabs button").forEach(function (b) {
    b.addEventListener("click", function () { showScreen(b.getAttribute("data-screen")); });
  });
  document.querySelectorAll("[data-goto]").forEach(function (b) {
    b.addEventListener("click", function () { showScreen(b.getAttribute("data-goto")); });
  });

  /* ---------- 起動 ---------- */
  var saved = null;
  try { saved = window.localStorage.getItem(LANG_KEY); } catch (e) { saved = null; }
  renderManualChips();
  applyLang(saved === "ja" ? "ja" : "en");
  if (auth && auth.isSignedIn()) {
    showApp();
  } else {
    showLogin(auth ? null : "auth_err_no_config", auth ? null : "error");
  }
})();
