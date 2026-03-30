"use strict";

const { describe, it, mock } = require("node:test");
const assert = require("node:assert/strict");

// We test the plugin by calling its exported functions with a mock context.
// The plugin requires "tobira", so we need to make it resolvable.
// We'll use a symlink approach or test the logic directly.

// Instead of mocking the module, we'll test by creating a plugin context
// that already has .client set (which is what register() does).

const plugin = (() => {
  // Temporarily override require to provide tobira
  const Module = require("node:module");
  const originalResolve = Module._resolveFilename;
  Module._resolveFilename = function (request, ...args) {
    if (request === "tobira") {
      return require.resolve("../../../js/src/index.js");
    }
    return originalResolve.call(this, request, ...args);
  };
  const p = require("../plugins/tobira");
  Module._resolveFilename = originalResolve;
  return p;
})();

function createMockConnection({
  bodytext = "test email body",
  ct = "text/plain",
} = {}) {
  return {
    transaction: {
      body: {
        ct,
        bodytext,
        children: [],
      },
      results: {
        add: mock.fn(),
      },
    },
    logerror: mock.fn(),
  };
}

describe("tobira haraka plugin", () => {
  describe("register", () => {
    it("should load config and register data_post hook", () => {
      const ctx = {
        config: {
          get: mock.fn(() => ({
            main: {
              url: "http://localhost:8000",
              timeout: "5000",
              threshold: "0.5",
              reject_spam: true,
            },
          })),
        },
        register_hook: mock.fn(),
      };

      plugin.register.call(ctx);

      assert.ok(ctx.client);
      assert.equal(ctx.threshold, 0.5);
      assert.equal(ctx.rejectSpam, true);
      assert.equal(ctx.register_hook.mock.calls.length, 2);
      assert.deepEqual(ctx.register_hook.mock.calls[0].arguments, [
        "mail",
        "enable_body_parse",
      ]);
      assert.deepEqual(ctx.register_hook.mock.calls[1].arguments, [
        "data_post",
        "check_spam",
      ]);
    });

    it("should use default values when config main is empty", () => {
      const ctx = {
        config: {
          get: mock.fn(() => ({})),
        },
        register_hook: mock.fn(),
      };

      plugin.register.call(ctx);

      assert.ok(ctx.client);
      assert.equal(ctx.client.baseUrl, "http://127.0.0.1:8000");
      assert.equal(ctx.client.timeout, 5000);
      assert.equal(ctx.threshold, 0.5);
      assert.equal(ctx.rejectSpam, true);
    });
  });

  describe("enable_body_parse", () => {
    it("should set parse_body to true on transaction", (_, done) => {
      const connection = { transaction: { parse_body: false } };
      plugin.enable_body_parse.call({}, (action) => {
        assert.equal(action, undefined);
        assert.equal(connection.transaction.parse_body, true);
        done();
      }, connection);
    });
  });

  describe("check_spam", () => {
    it("should call next() when no transaction", (_, done) => {
      const ctx = { client: { predict: mock.fn() }, threshold: 0.5, rejectSpam: true };
      plugin.check_spam.call(ctx, () => done(), { transaction: null });
    });

    it("should pass ham messages", async () => {
      const predictMock = mock.fn(async () => ({
        label: "ham",
        score: 0.95,
        labels: { ham: 0.95, spam: 0.05 },
      }));
      const ctx = { client: { predict: predictMock }, threshold: 0.5, rejectSpam: true };
      const connection = createMockConnection();

      await new Promise((resolve) => {
        plugin.check_spam.call(ctx, (action) => {
          assert.equal(action, undefined);
          const addCall = connection.transaction.results.add.mock.calls[0];
          assert.equal(addCall.arguments[1].label, "ham");
          assert.ok(addCall.arguments[1].pass);
          resolve();
        }, connection);
      });
    });

    it("should reject spam messages when reject_spam is true", async () => {
      const predictMock = mock.fn(async () => ({
        label: "spam",
        score: 0.9,
        labels: { ham: 0.1, spam: 0.9 },
      }));
      const ctx = { client: { predict: predictMock }, threshold: 0.5, rejectSpam: true };
      const connection = createMockConnection();

      globalThis.DENY = 902;
      await new Promise((resolve) => {
        plugin.check_spam.call(ctx, (action, msg) => {
          assert.equal(action, 902);
          assert.equal(msg, "Message detected as spam");
          delete globalThis.DENY;
          resolve();
        }, connection);
      });
    });

    it("should not reject spam when reject_spam is false", async () => {
      const predictMock = mock.fn(async () => ({
        label: "spam",
        score: 0.9,
        labels: { ham: 0.1, spam: 0.9 },
      }));
      const ctx = { client: { predict: predictMock }, threshold: 0.5, rejectSpam: false };
      const connection = createMockConnection();

      await new Promise((resolve) => {
        plugin.check_spam.call(ctx, (action) => {
          assert.equal(action, undefined);
          resolve();
        }, connection);
      });
    });

    it("should call next() on API error and add fail result", async () => {
      const predictMock = mock.fn(async () => {
        throw new Error("Connection refused");
      });
      const ctx = { client: { predict: predictMock }, threshold: 0.5, rejectSpam: true };
      const connection = createMockConnection();

      await new Promise((resolve) => {
        plugin.check_spam.call(ctx, (action) => {
          assert.equal(action, undefined);
          assert.equal(connection.logerror.mock.calls.length, 1);
          // Verify that results.add was called with fail info
          const addCall = connection.transaction.results.add.mock.calls[0];
          assert.equal(addCall.arguments[1].fail, "api_error");
          assert.equal(addCall.arguments[1].err, "Connection refused");
          resolve();
        }, connection);
      });
    });

    it("should not reject spam below threshold", async () => {
      const predictMock = mock.fn(async () => ({
        label: "spam",
        score: 0.6,
        labels: { ham: 0.4, spam: 0.6 },
      }));
      const ctx = { client: { predict: predictMock }, threshold: 0.8, rejectSpam: true };
      const connection = createMockConnection();

      await new Promise((resolve) => {
        plugin.check_spam.call(ctx, (action) => {
          assert.equal(action, undefined);
          resolve();
        }, connection);
      });
    });

    it("should handle empty body", (_, done) => {
      const ctx = { client: { predict: mock.fn() }, threshold: 0.5, rejectSpam: true };
      const connection = {
        transaction: {
          body: null,
          results: { add: mock.fn() },
        },
        logerror: mock.fn(),
      };

      plugin.check_spam.call(ctx, () => {
        assert.equal(ctx.client.predict.mock.calls.length, 0);
        done();
      }, connection);
    });

    it("should collect text from multipart body with children", async () => {
      const predictMock = mock.fn(async () => ({
        label: "ham",
        score: 0.9,
        labels: { ham: 0.9, spam: 0.1 },
      }));
      const ctx = { client: { predict: predictMock }, threshold: 0.5, rejectSpam: true };
      const connection = {
        transaction: {
          body: {
            ct: "multipart/mixed",
            bodytext: "",
            children: [
              { ct: "text/plain", bodytext: "Hello", children: [] },
              { ct: "text/html", bodytext: "<p>World</p>", children: [] },
            ],
          },
          results: { add: mock.fn() },
        },
        logerror: mock.fn(),
      };

      await new Promise((resolve) => {
        plugin.check_spam.call(ctx, () => {
          const calledWith = predictMock.mock.calls[0].arguments[0];
          assert.ok(calledWith.includes("Hello"));
          assert.ok(calledWith.includes("<p>World</p>"));
          resolve();
        }, connection);
      });
    });

    it("should skip non-text content types", async () => {
      const predictMock = mock.fn(async () => ({
        label: "ham",
        score: 0.9,
        labels: { ham: 0.9, spam: 0.1 },
      }));
      const ctx = { client: { predict: predictMock }, threshold: 0.5, rejectSpam: true };
      const connection = {
        transaction: {
          body: {
            ct: "multipart/mixed",
            bodytext: "",
            children: [
              { ct: "text/plain", bodytext: "Visible text", children: [] },
              { ct: "image/png", bodytext: "binary data", children: [] },
            ],
          },
          results: { add: mock.fn() },
        },
        logerror: mock.fn(),
      };

      await new Promise((resolve) => {
        plugin.check_spam.call(ctx, () => {
          const calledWith = predictMock.mock.calls[0].arguments[0];
          assert.ok(calledWith.includes("Visible text"));
          assert.ok(!calledWith.includes("binary data"));
          resolve();
        }, connection);
      });
    });
  });
});
