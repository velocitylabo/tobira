"use strict";
// Accept all recipients — test/demo environment only
exports.hook_rcpt = function (next, connection, params) {
  return next(OK);
};
