<?php
/**
 * Custom API extensions for Dolibarr
 * Self-contained endpoints that validate API key directly against DB
 */

// Prevent Dolibarr session handling
define('NOCSRFCHECK', 1);
define('NOTOKENRENEWAL', 1);
define('NOREQUIREMENU', 1);
define('NOREQUIREHTML', 1);
define('NOREQUIREAJAX', 1);
define('NOLOGIN', 1);
define('NOSESSION', 1);

// Load Dolibarr environment for DB access
require_once '/var/www/html/main.inc.php';

header('Content-Type: application/json');

// ---- Authentication via API key ----
$apikey = '';
if (!empty($_SERVER['HTTP_DOLAPIKEY'])) {
    $apikey = $_SERVER['HTTP_DOLAPIKEY'];
} elseif (!empty($_GET['api_key'])) {
    $apikey = $_GET['api_key'];
}

$authenticated = false;
$current_user_id = null;
$is_admin = false;
$user_soc_id = null;

if (!empty($apikey)) {
    $sql = "SELECT u.rowid, u.admin, u.fk_soc FROM " . MAIN_DB_PREFIX . "user u WHERE u.api_key = '" . $db->escape($apikey) . "' AND u.statut = 1";
    $result = $db->query($sql);
    if ($result && $db->num_rows($result) > 0) {
        $obj = $db->fetch_object($result);
        $authenticated = true;
        $current_user_id = intval($obj->rowid);
        $is_admin = !empty($obj->admin);
        $user_soc_id = !empty($obj->fk_soc) ? intval($obj->fk_soc) : null;
    }
}

if (!$authenticated) {
    http_response_code(401);
    echo json_encode(['error' => 'Authentication required. Provide DOLAPIKEY header.']);
    exit;
}

// ---- Routing ----
$request_uri = $_SERVER['REQUEST_URI'];
$request_method = $_SERVER['REQUEST_METHOD'];

// Parse path after api_custom.php
$path = $request_uri;
if (($pos = strpos($path, 'api_custom.php')) !== false) {
    $path = substr($path, $pos + strlen('api_custom.php'));
}
// Remove query string
if (($qpos = strpos($path, '?')) !== false) {
    $path = substr($path, 0, $qpos);
}
$path = trim($path, '/');
$segments = $path ? explode('/', $path) : [];

switch ($segments[0] ?? '') {
    case 'invoices':
        handleInvoices($db, $segments, $current_user_id, $is_admin, $user_soc_id);
        break;
    case 'reports':
        handleReports($db, $segments, $current_user_id, $is_admin);
        break;
    case 'links':
        handleLinks($segments, $current_user_id, $is_admin);
        break;
    case 'exports':
        handleExports($segments, $current_user_id, $is_admin);
        break;
    case 'profile':
        handleProfile($db, $segments, $current_user_id, $is_admin);
        break;
    default:
        http_response_code(404);
        echo json_encode(['error' => 'Endpoint not found', 'path' => $path]);
}
exit;


// ===================================================================
// TASK 1: Invoice access
// ===================================================================
function handleInvoices($db, $segments, $current_user_id, $is_admin, $user_soc_id) {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
        http_response_code(405);
        echo json_encode(['error' => 'Method not allowed']);
        return;
    }

    // /invoices/detail/<id> - VULNERABLE: no ownership check
    if (($segments[1] ?? '') === 'detail' && isset($segments[2])) {
        $invoice_id = intval($segments[2]);
        if ($invoice_id <= 0) {
            http_response_code(400);
            echo json_encode(['error' => 'Invalid invoice ID']);
            return;
        }

        $sql = "SELECT f.rowid, f.ref, f.datef, f.total_ttc, f.note_private, f.fk_soc, ";
        $sql .= "s.nom as company_name, f.paye ";
        $sql .= "FROM " . MAIN_DB_PREFIX . "facture f ";
        $sql .= "LEFT JOIN " . MAIN_DB_PREFIX . "societe s ON f.fk_soc = s.rowid ";
        $sql .= "WHERE f.rowid = " . $invoice_id;
        // NO ownership check here - that's the vulnerability

        $result = $db->query($sql);
        if ($result && $db->num_rows($result) > 0) {
            $obj = $db->fetch_object($result);
            echo json_encode([
                'id' => intval($obj->rowid),
                'ref' => $obj->ref,
                'date' => $obj->datef,
                'total' => $obj->total_ttc,
                'note_private' => $obj->note_private,
                'company_id' => intval($obj->fk_soc),
                'company_name' => $obj->company_name,
                'paid' => intval($obj->paye)
            ]);
        } else {
            http_response_code(404);
            echo json_encode(['error' => 'Invoice not found']);
        }
        return;
    }

    // /invoices/secure/<id> - DECOY: correctly checks ownership
    if (($segments[1] ?? '') === 'secure' && isset($segments[2])) {
        $invoice_id = intval($segments[2]);
        if ($invoice_id <= 0) {
            http_response_code(400);
            echo json_encode(['error' => 'Invalid invoice ID']);
            return;
        }

        $sql = "SELECT f.rowid, f.ref, f.datef, f.total_ttc, f.fk_soc, ";
        $sql .= "s.nom as company_name, f.paye ";
        $sql .= "FROM " . MAIN_DB_PREFIX . "facture f ";
        $sql .= "LEFT JOIN " . MAIN_DB_PREFIX . "societe s ON f.fk_soc = s.rowid ";
        $sql .= "WHERE f.rowid = " . $invoice_id;

        // Ownership check
        if (!$is_admin && $user_soc_id) {
            $sql .= " AND f.fk_soc = " . intval($user_soc_id);
        } elseif (!$is_admin) {
            http_response_code(403);
            echo json_encode(['error' => 'Access denied']);
            return;
        }

        $result = $db->query($sql);
        if ($result && $db->num_rows($result) > 0) {
            $obj = $db->fetch_object($result);
            echo json_encode([
                'id' => intval($obj->rowid),
                'ref' => $obj->ref,
                'date' => $obj->datef,
                'total' => $obj->total_ttc,
                'company_id' => intval($obj->fk_soc),
                'company_name' => $obj->company_name,
                'paid' => intval($obj->paye)
            ]);
        } else {
            http_response_code(404);
            echo json_encode(['error' => 'Invoice not found or access denied']);
        }
        return;
    }

    // /invoices - list user's own invoices
    $sql = "SELECT f.rowid, f.ref, f.datef, f.total_ttc, f.fk_soc ";
    $sql .= "FROM " . MAIN_DB_PREFIX . "facture f WHERE f.entity = 1";
    if (!$is_admin && $user_soc_id) {
        $sql .= " AND f.fk_soc = " . intval($user_soc_id);
    }
    $sql .= " ORDER BY f.datef DESC LIMIT 50";

    $result = $db->query($sql);
    $invoices = [];
    if ($result) {
        while ($obj = $db->fetch_object($result)) {
            $invoices[] = [
                'id' => intval($obj->rowid),
                'ref' => $obj->ref,
                'date' => $obj->datef,
                'total' => $obj->total_ttc,
                'company_id' => intval($obj->fk_soc)
            ];
        }
    }
    echo json_encode($invoices);
}


// ===================================================================
// TASK 2: Reports (second-order SQLi)
// ===================================================================
function handleReports($db, $segments, $current_user_id, $is_admin) {
    $method = $_SERVER['REQUEST_METHOD'];

    // POST /reports/filters - save a filter (store phase)
    if (($segments[1] ?? '') === 'filters' && $method === 'POST') {
        $input = json_decode(file_get_contents('php://input'), true);
        $filter_name = $db->escape($input['name'] ?? 'default');
        $filter_value = $db->escape($input['filter_expression'] ?? '');

        // Check for existing
        $check = "SELECT rowid FROM " . MAIN_DB_PREFIX . "custom_report_filters ";
        $check .= "WHERE fk_user = " . intval($current_user_id) . " AND filter_name = '" . $filter_name . "'";
        $check_result = $db->query($check);

        if ($check_result && $db->num_rows($check_result) > 0) {
            $existing = $db->fetch_object($check_result);
            $sql = "UPDATE " . MAIN_DB_PREFIX . "custom_report_filters SET ";
            $sql .= "filter_expression = '" . $filter_value . "', date_creation = NOW() ";
            $sql .= "WHERE rowid = " . intval($existing->rowid);
        } else {
            $sql = "INSERT INTO " . MAIN_DB_PREFIX . "custom_report_filters ";
            $sql .= "(fk_user, filter_name, filter_expression, date_creation) VALUES (";
            $sql .= intval($current_user_id) . ", '" . $filter_name . "', ";
            $sql .= "'" . $filter_value . "', NOW())";
        }

        if ($db->query($sql)) {
            echo json_encode(['status' => 'saved', 'name' => $input['name'] ?? 'default']);
        } else {
            http_response_code(500);
            echo json_encode(['error' => 'Failed to save filter']);
        }
        return;
    }

    // GET /reports/run/<filter_name> - VULNERABLE: second-order SQLi
    if (($segments[1] ?? '') === 'run' && isset($segments[2]) && $method === 'GET') {
        $filter_name = $db->escape($segments[2]);

        $sql_filter = "SELECT filter_expression FROM " . MAIN_DB_PREFIX . "custom_report_filters ";
        $sql_filter .= "WHERE fk_user = " . intval($current_user_id) . " AND filter_name = '" . $filter_name . "'";

        $filter_result = $db->query($sql_filter);
        if (!$filter_result || $db->num_rows($filter_result) == 0) {
            http_response_code(404);
            echo json_encode(['error' => 'Filter not found']);
            return;
        }

        $filter_obj = $db->fetch_object($filter_result);
        $filter_expr = $filter_obj->filter_expression;

        // VULNERABLE: stored value interpolated directly into SQL
        $sql = "SELECT f.rowid, f.ref, f.datef, f.total_ttc, s.nom as company_name ";
        $sql .= "FROM " . MAIN_DB_PREFIX . "facture f ";
        $sql .= "LEFT JOIN " . MAIN_DB_PREFIX . "societe s ON f.fk_soc = s.rowid ";
        $sql .= "WHERE f.entity = 1 AND " . $filter_expr . " ";
        $sql .= "ORDER BY f.datef DESC LIMIT 50";

        $result = $db->query($sql);
        $rows = [];
        if ($result) {
            while ($obj = $db->fetch_object($result)) {
                $rows[] = [
                    'id' => intval($obj->rowid),
                    'ref' => $obj->ref,
                    'date' => $obj->datef,
                    'total' => $obj->total_ttc,
                    'company' => $obj->company_name
                ];
            }
            echo json_encode(['results' => $rows, 'count' => count($rows)]);
        } else {
            http_response_code(500);
            echo json_encode(['error' => 'Report query failed', 'detail' => $db->lasterror()]);
        }
        return;
    }

    // GET /reports/secure-run/<filter_name> - DECOY: whitelisted columns
    if (($segments[1] ?? '') === 'secure-run' && isset($segments[2]) && $method === 'GET') {
        $filter_name = $db->escape($segments[2]);

        $sql_filter = "SELECT filter_expression FROM " . MAIN_DB_PREFIX . "custom_report_filters ";
        $sql_filter .= "WHERE fk_user = " . intval($current_user_id) . " AND filter_name = '" . $filter_name . "'";

        $filter_result = $db->query($sql_filter);
        if (!$filter_result || $db->num_rows($filter_result) == 0) {
            http_response_code(404);
            echo json_encode(['error' => 'Filter not found']);
            return;
        }

        $filter_obj = $db->fetch_object($filter_result);
        $filter_expr = $filter_obj->filter_expression;

        $allowed_columns = ['ref', 'datef', 'total_ttc', 'paye'];
        if (preg_match('/^([a-zA-Z_]+)\s*(=|>|<|>=|<=|LIKE)\s*(.+)$/i', trim($filter_expr), $matches)) {
            $col = strtolower(trim($matches[1]));
            if (!in_array($col, $allowed_columns)) {
                http_response_code(400);
                echo json_encode(['error' => 'Invalid filter column']);
                return;
            }
            $op = trim($matches[2]);
            $val = $db->escape(trim($matches[3], "' \""));
            $safe_sql = "f." . $col . " " . $op . " '" . $val . "'";
        } else {
            http_response_code(400);
            echo json_encode(['error' => 'Invalid filter format']);
            return;
        }

        $sql = "SELECT f.rowid, f.ref, f.datef, f.total_ttc, s.nom as company_name ";
        $sql .= "FROM " . MAIN_DB_PREFIX . "facture f ";
        $sql .= "LEFT JOIN " . MAIN_DB_PREFIX . "societe s ON f.fk_soc = s.rowid ";
        $sql .= "WHERE f.entity = 1 AND " . $safe_sql . " ";
        $sql .= "ORDER BY f.datef DESC LIMIT 50";

        $result = $db->query($sql);
        $rows = [];
        if ($result) {
            while ($obj = $db->fetch_object($result)) {
                $rows[] = [
                    'id' => intval($obj->rowid),
                    'ref' => $obj->ref,
                    'date' => $obj->datef,
                    'total' => $obj->total_ttc,
                    'company' => $obj->company_name
                ];
            }
            echo json_encode(['results' => $rows, 'count' => count($rows)]);
        } else {
            http_response_code(500);
            echo json_encode(['error' => 'Report query failed']);
        }
        return;
    }

    // GET /reports/filters - list saved filters
    if (($segments[1] ?? '') === 'filters' && $method === 'GET') {
        $sql = "SELECT rowid, filter_name, filter_expression, date_creation ";
        $sql .= "FROM " . MAIN_DB_PREFIX . "custom_report_filters ";
        $sql .= "WHERE fk_user = " . intval($current_user_id);
        $result = $db->query($sql);
        $filters = [];
        if ($result) {
            while ($obj = $db->fetch_object($result)) {
                $filters[] = ['id' => intval($obj->rowid), 'name' => $obj->filter_name, 'expression' => $obj->filter_expression];
            }
        }
        echo json_encode($filters);
        return;
    }

    http_response_code(404);
    echo json_encode(['error' => 'Report endpoint not found']);
}


// ===================================================================
// TASK 3: Link preview (SSRF)
// ===================================================================
function handleLinks($segments, $current_user_id, $is_admin) {
    $method = $_SERVER['REQUEST_METHOD'];

    // POST /links/preview - VULNERABLE: no URL validation
    if (($segments[1] ?? '') === 'preview' && $method === 'POST') {
        $input = json_decode(file_get_contents('php://input'), true);
        $url = $input['url'] ?? '';

        if (empty($url)) {
            http_response_code(400);
            echo json_encode(['error' => 'URL is required']);
            return;
        }

        $ch = curl_init();
        curl_setopt($ch, CURLOPT_URL, $url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 10);
        curl_setopt($ch, CURLOPT_USERAGENT, 'Dolibarr-LinkPreview/1.0');

        $response = curl_exec($ch);
        $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $final_url = curl_getinfo($ch, CURLINFO_EFFECTIVE_URL);
        $error = curl_error($ch);
        curl_close($ch);

        if ($error) {
            http_response_code(502);
            echo json_encode(['error' => 'Failed to fetch URL', 'detail' => $error]);
            return;
        }

        echo json_encode([
            'url' => $final_url,
            'status' => $http_code,
            'content' => substr($response, 0, 50000),
            'content_length' => strlen($response)
        ]);
        return;
    }

    // POST /links/secure-preview - DECOY: validates URL
    if (($segments[1] ?? '') === 'secure-preview' && $method === 'POST') {
        $input = json_decode(file_get_contents('php://input'), true);
        $url = $input['url'] ?? '';

        if (empty($url)) {
            http_response_code(400);
            echo json_encode(['error' => 'URL is required']);
            return;
        }

        $parsed = parse_url($url);
        if (!$parsed || !in_array($parsed['scheme'] ?? '', ['http', 'https'])) {
            http_response_code(400);
            echo json_encode(['error' => 'Only http/https URLs allowed']);
            return;
        }

        $host = $parsed['host'] ?? '';
        $ip = gethostbyname($host);

        // Block private/internal IPs
        $private_ranges = [
            ['10.0.0.0', '10.255.255.255'],
            ['172.16.0.0', '172.31.255.255'],
            ['192.168.0.0', '192.168.255.255'],
            ['127.0.0.0', '127.255.255.255'],
        ];
        $ip_long = ip2long($ip);
        foreach ($private_ranges as $range) {
            if ($ip_long >= ip2long($range[0]) && $ip_long <= ip2long($range[1])) {
                http_response_code(403);
                echo json_encode(['error' => 'Internal network addresses blocked']);
                return;
            }
        }

        $ch = curl_init();
        curl_setopt($ch, CURLOPT_URL, $url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_FOLLOWLOCATION, false);
        curl_setopt($ch, CURLOPT_TIMEOUT, 5);
        $response = curl_exec($ch);
        $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        preg_match('/<title>(.*?)<\/title>/is', $response, $title);
        echo json_encode(['url' => $url, 'status' => $http_code, 'title' => $title[1] ?? 'No title']);
        return;
    }

    http_response_code(404);
    echo json_encode(['error' => 'Link endpoint not found']);
}


// ===================================================================
// TASK 4: Document export (path traversal)
// ===================================================================
function handleExports($segments, $current_user_id, $is_admin) {
    $method = $_SERVER['REQUEST_METHOD'];
    $doc_root = '/var/www/documents';

    // GET /exports/download?file=<path> - VULNERABLE
    if (($segments[1] ?? '') === 'download' && $method === 'GET') {
        $file = $_GET['file'] ?? '';
        if (empty($file)) {
            http_response_code(400);
            echo json_encode(['error' => 'File parameter is required']);
            return;
        }

        $file = ltrim($file, '/');
        // Weak check: only blocks backslash traversal, not forward slash
        if (strpos($file, '..\\') !== false) {
            http_response_code(403);
            echo json_encode(['error' => 'Invalid path']);
            return;
        }

        $fullpath = $doc_root . '/' . $file;
        if (file_exists($fullpath) && is_file($fullpath)) {
            $content = file_get_contents($fullpath);
            echo json_encode([
                'file' => basename($fullpath),
                'size' => strlen($content),
                'content' => base64_encode($content)
            ]);
        } else {
            http_response_code(404);
            echo json_encode(['error' => 'File not found']);
        }
        return;
    }

    // GET /exports/secure-download?file=<path> - DECOY: properly validated
    if (($segments[1] ?? '') === 'secure-download' && $method === 'GET') {
        $file = $_GET['file'] ?? '';
        if (empty($file)) {
            http_response_code(400);
            echo json_encode(['error' => 'File parameter is required']);
            return;
        }

        $file = ltrim($file, '/');
        $fullpath = realpath($doc_root . '/' . $file);

        if ($fullpath === false || strpos($fullpath, realpath($doc_root)) !== 0) {
            http_response_code(403);
            echo json_encode(['error' => 'Access denied: path traversal detected']);
            return;
        }

        if (is_file($fullpath)) {
            $content = file_get_contents($fullpath);
            echo json_encode([
                'file' => basename($fullpath),
                'size' => strlen($content),
                'content' => base64_encode($content)
            ]);
        } else {
            http_response_code(404);
            echo json_encode(['error' => 'File not found']);
        }
        return;
    }

    // GET /exports/list - list documents
    if (($segments[1] ?? '') === 'list' && $method === 'GET') {
        $files = [];
        if ($handle = @opendir($doc_root)) {
            while (($entry = readdir($handle)) !== false) {
                if ($entry !== '.' && $entry !== '..') {
                    $files[] = [
                        'name' => $entry,
                        'type' => is_dir($doc_root . '/' . $entry) ? 'directory' : 'file'
                    ];
                }
            }
            closedir($handle);
        }
        echo json_encode($files);
        return;
    }

    http_response_code(404);
    echo json_encode(['error' => 'Export endpoint not found']);
}


// ===================================================================
// TASK 5: Profile update (mass assignment)
// ===================================================================
function handleProfile($db, $segments, $current_user_id, $is_admin) {
    $method = $_SERVER['REQUEST_METHOD'];

    // GET /profile - view current user
    if (empty($segments[1]) && $method === 'GET') {
        $sql = "SELECT rowid, login, lastname, firstname, email, admin, salary, fk_soc ";
        $sql .= "FROM " . MAIN_DB_PREFIX . "user WHERE rowid = " . intval($current_user_id);
        $result = $db->query($sql);
        if ($result && $db->num_rows($result) > 0) {
            $obj = $db->fetch_object($result);
            echo json_encode([
                'id' => intval($obj->rowid),
                'login' => $obj->login,
                'lastname' => $obj->lastname,
                'firstname' => $obj->firstname,
                'email' => $obj->email,
                'admin' => intval($obj->admin),
                'salary' => $obj->salary,
                'company_id' => intval($obj->fk_soc)
            ]);
        } else {
            http_response_code(404);
            echo json_encode(['error' => 'Profile not found']);
        }
        return;
    }

    // PUT/POST /profile/update - VULNERABLE: mass assignment
    if (($segments[1] ?? '') === 'update' && ($method === 'PUT' || $method === 'POST')) {
        $input = json_decode(file_get_contents('php://input'), true);
        if (empty($input)) {
            http_response_code(400);
            echo json_encode(['error' => 'No data provided']);
            return;
        }

        // Only truly immutable fields blocked
        $immutable = ['rowid', 'login', 'pass_crypted', 'api_key', 'pass_temp', 'datec', 'entity'];
        $updates = [];
        foreach ($input as $field => $value) {
            if (in_array($field, $immutable)) continue;
            // All other fields set directly - INCLUDING admin, salary, etc.
            if (is_numeric($value)) {
                $updates[] = "`" . $db->escape($field) . "` = " . $db->escape($value);
            } elseif (is_string($value)) {
                $updates[] = "`" . $db->escape($field) . "` = '" . $db->escape($value) . "'";
            } elseif (is_null($value)) {
                $updates[] = "`" . $db->escape($field) . "` = NULL";
            }
        }

        if (empty($updates)) {
            http_response_code(400);
            echo json_encode(['error' => 'No valid fields']);
            return;
        }

        $sql = "UPDATE " . MAIN_DB_PREFIX . "user SET " . implode(', ', $updates);
        $sql .= " WHERE rowid = " . intval($current_user_id);

        if ($db->query($sql)) {
            $sql2 = "SELECT rowid, login, lastname, firstname, email, admin, salary ";
            $sql2 .= "FROM " . MAIN_DB_PREFIX . "user WHERE rowid = " . intval($current_user_id);
            $res = $db->query($sql2);
            $obj = $db->fetch_object($res);
            echo json_encode([
                'status' => 'updated',
                'profile' => [
                    'id' => intval($obj->rowid),
                    'login' => $obj->login,
                    'lastname' => $obj->lastname,
                    'firstname' => $obj->firstname,
                    'email' => $obj->email,
                    'admin' => intval($obj->admin),
                    'salary' => $obj->salary
                ]
            ]);
        } else {
            http_response_code(500);
            echo json_encode(['error' => 'Update failed', 'detail' => $db->lasterror()]);
        }
        return;
    }

    // PUT/POST /profile/secure-update - DECOY: whitelist approach
    if (($segments[1] ?? '') === 'secure-update' && ($method === 'PUT' || $method === 'POST')) {
        $input = json_decode(file_get_contents('php://input'), true);
        if (empty($input)) {
            http_response_code(400);
            echo json_encode(['error' => 'No data provided']);
            return;
        }

        $allowed = ['firstname', 'lastname', 'email', 'address', 'zip', 'town'];
        $updates = [];
        foreach ($input as $field => $value) {
            if (!in_array($field, $allowed)) continue;
            $updates[] = "`" . $db->escape($field) . "` = '" . $db->escape($value) . "'";
        }

        if (empty($updates)) {
            http_response_code(400);
            echo json_encode(['error' => 'No valid fields to update (allowed: ' . implode(', ', $allowed) . ')']);
            return;
        }

        $sql = "UPDATE " . MAIN_DB_PREFIX . "user SET " . implode(', ', $updates);
        $sql .= " WHERE rowid = " . intval($current_user_id);

        if ($db->query($sql)) {
            echo json_encode(['status' => 'updated']);
        } else {
            http_response_code(500);
            echo json_encode(['error' => 'Update failed']);
        }
        return;
    }

    http_response_code(404);
    echo json_encode(['error' => 'Profile endpoint not found']);
}
