$ErrorActionPreference = "Stop"

$baseUri = "http://localhost:8100"
$loginBody = @{email="demo@finkit.example"; password="demo123456"} | ConvertTo-Json
$loginResp = Invoke-RestMethod -Uri "$baseUri/api/auth/login" -Method POST -Body $loginBody -ContentType "application/json"
$token = $loginResp.access_token
$headers = @{Authorization="Bearer $token"; "Content-Type"="application/json"}

Write-Host "=== Creating Accounts ===" -ForegroundColor Cyan

$accounts = @(
    @{name="Salary Account"; currency="CNY"; initial_balance=5000; account_type="checking"; sort_order=1},
    @{name="Savings Account"; currency="CNY"; initial_balance=20000; account_type="savings"; sort_order=2},
    @{name="Investment Account"; currency="CNY"; initial_balance=50000; account_type="investment"; sort_order=3},
    @{name="Cash"; currency="CNY"; initial_balance=2000; account_type="cash"; sort_order=4}
)

$accountIds = @{}
foreach($acc in $accounts) {
    $resp = Invoke-RestMethod -Uri "$baseUri/api/accounts" -Method POST -Body ($acc | ConvertTo-Json) -Headers $headers
    $accountIds[$acc.name] = $resp.id
    Write-Host "Created: $($acc.name)"
}

Write-Host "`n=== Creating Categories ===" -ForegroundColor Cyan

$categories = @(
    @{type="income"; name="Salary"; color="#4CAF50"; icon="briefcase"; sort_order=1},
    @{type="income"; name="Bonus"; color="#8BC34A"; icon="gift"; sort_order=2},
    @{type="expense"; name="Food"; color="#FF9800"; icon="utensils"; sort_order=1},
    @{type="expense"; name="Transport"; color="#2196F3"; icon="car"; sort_order=2},
    @{type="expense"; name="Housing"; color="#9C27B0"; icon="home"; sort_order=3},
    @{type="expense"; name="Shopping"; color="#E91E63"; icon="shopping-bag"; sort_order=4}
)

$catIds = @{}
foreach($cat in $categories) {
    $resp = Invoke-RestMethod -Uri "$baseUri/api/categories" -Method POST -Body ($cat | ConvertTo-Json) -Headers $headers
    $catIds["${cat.type}-${cat.name}"] = $resp.id
    Write-Host "Created: $($cat.type)/$($cat.name)"
}

Write-Host "`n=== Generating Transactions ===" -ForegroundColor Cyan

$today = Get-Date
$transactions = @()

for($m = 0; $m -lt 6; $m++) {
    $date = $today.AddMonths(-$m).AddDays(1-$today.Day)
    if($date -le $today) {
        $transactions += @{
            date = $date.ToString("yyyy-MM-dd")
            type = "income"
            amount = 15000
            account_id = $accountIds["Salary Account"]
            category_id = $catIds["income-Salary"]
            description = "Monthly Salary"
            remark = ""
        }
    }
}

for($i = 0; $i -lt 50; $i++) {
    $date = $today.AddDays(-[int](Get-Random -Maximum 60))
    $txnType = Get-Random -Maximum 10
    if($txnType -lt 3) {
        $catKey = "expense-Food"
        $amount = 30 + [int](Get-Random -Maximum 150)
        $desc = "Daily Meals"
    } elseif($txnType -lt 5) {
        $catKey = "expense-Transport"
        $amount = 5 + [int](Get-Random -Maximum 50)
        $desc = "Public Transit"
    } elseif($txnType -lt 7) {
        $catKey = "expense-Shopping"
        $amount = 50 + [int](Get-Random -Maximum 500)
        $desc = "Online Shopping"
    } else {
        $catKey = "expense-Housing"
        $amount = 2000 + [int](Get-Random -Maximum 1000)
        $desc = "Rent"
    }
    
    $transactions += @{
        date = $date.ToString("yyyy-MM-dd")
        type = "expense"
        amount = $amount
        account_id = $accountIds["Salary Account"]
        category_id = $catIds[$catKey]
        description = $desc
        remark = ""
    }
}

$bonusDate = $today.AddDays(-15)
$transactions += @{
    date = $bonusDate.ToString("yyyy-MM-dd")
    type = "income"
    amount = 5000
    account_id = $accountIds["Salary Account"]
    category_id = $catIds["income-Bonus"]
    description = "Project Bonus"
    remark = ""
}

for($m = 0; $m -lt 3; $m++) {
    $date = $today.AddMonths(-$m).AddDays(5-$today.Day)
    if($date -le $today) {
        $transactions += @{
            date = $date.ToString("yyyy-MM-dd")
            type = "transfer"
            amount = 3000
            account_id = $accountIds["Salary Account"]
            dest_account_id = $accountIds["Savings Account"]
            description = "Monthly Savings"
            remark = ""
        }
    }
}

Write-Host "Writing $($transactions.Count) transactions..."
$success = 0
foreach($txn in $transactions) {
    try {
        Invoke-RestMethod -Uri "$baseUri/api/transactions" -Method POST -Body ($txn | ConvertTo-Json) -Headers $headers | Out-Null
        $success++
    } catch {
        Write-Host "Failed: $_"
    }
}
Write-Host "Successfully wrote $success/$($transactions.Count) transactions"

Write-Host "`n=== Creating Investments ===" -ForegroundColor Cyan

$investments = @(
    @{name="HS300 ETF"; investment_type="fund"; symbol="510300"; exchange="SH"; underlying_asset_type="Stock"; asset_class="A-Share"; quantity=1000; purchase_price=4.5; current_price=4.8; purchase_date="2025-01-15"; notes="Core holding"},
    @{name="Gold ETF"; investment_type="fund"; symbol="518880"; exchange="SH"; underlying_asset_type="Commodity"; asset_class="Gold"; quantity=500; purchase_price=5.2; current_price=5.5; purchase_date="2025-03-20"; notes="Hedge asset"},
    @{name="Money Market Fund"; investment_type="fund"; symbol="000011"; exchange="FUND_CN"; underlying_asset_type="Money Market"; asset_class="Money Market"; quantity=50000; purchase_price=1.0; current_price=1.0; purchase_date="2024-06-01"; notes="Liquidity management"; is_money_market=$true},
    @{name="US Tech ETF"; investment_type="fund"; symbol="QQQ"; exchange="US"; underlying_asset_type="Stock"; asset_class="US Stock"; quantity=200; purchase_price=380; current_price=420; purchase_date="2025-02-10"; notes="Overseas allocation"}
)

foreach($inv in $investments) {
    try {
        $resp = Invoke-RestMethod -Uri "$baseUri/api/investments" -Method POST -Body ($inv | ConvertTo-Json) -Headers $headers
        Write-Host "Created: $($inv.name)"
    } catch {
        Write-Host "Failed: $_"
    }
}

Write-Host "`n=== Creating Cash Flows ===" -ForegroundColor Cyan

$cashFlows = @(
    @{flow_type="deposit"; amount=45000; flow_date="2025-01-10"; account_id=$accountIds["Investment Account"]; notes="Initial investment"},
    @{flow_type="deposit"; amount=26000; flow_date="2025-03-15"; account_id=$accountIds["Investment Account"]; notes="Additional investment"},
    @{flow_type="deposit"; amount=10000; flow_date="2025-06-01"; account_id=$accountIds["Investment Account"]; notes="Quarterly investment"}
)

foreach($cf in $cashFlows) {
    try {
        Invoke-RestMethod -Uri "$baseUri/api/investments/cash-flows" -Method POST -Body ($cf | ConvertTo-Json) -Headers $headers | Out-Null
        Write-Host "Created: $($cf.flowType) $($cf.amount)"
    } catch {
        Write-Host "Failed: $_"
    }
}

Write-Host "`n=== DONE ===" -ForegroundColor Green
Write-Host "Demo account: demo@finkit.example"
Write-Host "Demo password: demo123456"
Write-Host "`nPlease screenshot:"
Write-Host "1. Dashboard - showing total assets and cash flow"
Write-Host "2. Bookkeeping - showing transaction list"
Write-Host "3. Statistics - showing charts"
Write-Host "4. Investments - showing portfolio"

