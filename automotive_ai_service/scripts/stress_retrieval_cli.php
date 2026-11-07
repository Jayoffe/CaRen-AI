<?php

/**
 * TEST HARNESS ONLY (not part of the application; lives outside Back-End).
 * Same as Back-End/tests/chat_retrieval_cli.php, plus a fixed "today" from CHAT_TEST_TODAY, so evaluation
 * sets written for a fixture date keep their meaning. Back-End code itself is not changed.
 */
require_once dirname(__DIR__, 2) . '/Back-End/tests/support/ChatFixtureSource.php';

$input = json_decode(stream_get_contents(STDIN), true);
if (!is_array($input) || !is_array($input['requests'] ?? null)) {
    fwrite(STDERR, "Expected a JSON object with a requests array.\n");
    exit(2);
}
$fixture = json_decode((string) file_get_contents($input['fixture_path']), true);
$today   = getenv('CHAT_TEST_TODAY') ?: null;

$out = array_map(static function ($request) use ($fixture, $today) {
    $source = new ChatFixtureSource($fixture);
    if (($request['op'] ?? null) === 'vocabulary') {
        return ChatRetrieval::vocabulary($source->vehicles(!empty($request['is_admin'])));
    }
    $viewer = $request['viewer'] ?? [];
    return ChatRetrieval::execute($request['plan'] ?? [], [
        'role'    => ($viewer['role'] ?? '') === 'admin' ? 'admin' : 'customer',
        'user_id' => (int) ($viewer['user_id'] ?? 0),
    ], $source, $today);
}, $input['requests']);

echo json_encode($out, JSON_UNESCAPED_UNICODE);
