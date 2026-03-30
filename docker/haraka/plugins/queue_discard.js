"use strict";
// Silently discard all mail — test/demo environment only
exports.hook_queue = function (next, connection) {
  return next(OK);
};
