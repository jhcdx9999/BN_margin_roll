def backtest(
    initial_funds,
    leverage,
    initial_price,
    total_price_increase,
    price_step,
    risk_line=1.1
):
    """
    Backtest the liquidation price and remaining principal after rolling over
    :param initial_funds: Initial own funds (USDT)
    :param leverage: Leverage multiplier
    :param initial_price: Initial price of DOGE
    :param total_price_increase: Total price increase of DOGE in percentage (e.g., 0.1 means 10%)
    :param price_step: Price increase step of DOGE (e.g., 0.01 means 1%)
    :param risk_line: Liquidation risk level (default is 1.1)
    :return: Liquidation price and remaining principal at liquidation
    """
    borrowed = initial_funds * (leverage - 1)  # Initial borrowed amount
    total_usdt = initial_funds + borrowed      # Total initial funds
    doge_quantity = total_usdt / initial_price  # Initial DOGE quantity

    cumulative_borrowed = borrowed  # Cumulative borrowed amount
    current_price = initial_price
    # Rolling over logic
    while current_price < initial_price * (1 + total_price_increase):
        current_price *= (1 + price_step)  # DOGE price increases by price_step
        # Calculate additional borrowable amount
        additional_borrowable = calculate_additional_borrowable(
            cumulative_borrowed, doge_quantity, current_price, leverage
        )
        # Update cumulative borrowed amount and DOGE holding
        cumulative_borrowed += additional_borrowable
        additional_doge = additional_borrowable / current_price
        doge_quantity += additional_doge
        # print(f"{round(current_price,4)} {int(doge_quantity)} {int(cumulative_borrowed)} {int(additional_borrowable)} {int(doge_quantity*current_price-cumulative_borrowed)}")

    # Liquidation price calculation
    liquidation_price = (cumulative_borrowed * risk_line) / doge_quantity

    # Remaining principal at liquidation = value of assets at liquidation price - total borrowed amount
    remaining_principal = (
        liquidation_price * doge_quantity - cumulative_borrowed
    )
    remaining_principal = max(remaining_principal, 0)  # Principal cannot be negative

    return {
        "final_price": current_price,
        "doge_quantity": doge_quantity,
        "cumulative_borrowed": cumulative_borrowed,
        "liquidation_price": liquidation_price,
        "remaining_principal": remaining_principal,
    }


def calculate_additional_borrowable(cumulative_borrowed, doge_quantity, current_price, leverage):
    """
    Calculate the additional borrowable amount of USDT when DOGE increases by a certain percentage
    :param cumulative_borrowed: Current cumulative borrowed amount (USDT)
    :param doge_quantity: Current holding of DOGE
    :param current_price: Current DOGE price (USDT)
    :param leverage: Leverage multiplier (e.g., 3 means 3x leverage)
    :return: Additional borrowable amount (USDT)
    """
    # Current net asset value
    net_asset_value = doge_quantity * current_price - cumulative_borrowed  # Net value
    max_total_borrowable = net_asset_value * (leverage - 1)  # Maximum total borrowable amount
    # Additional borrowable amount = maximum total borrowable amount - current cumulative borrowed
    additional_borrowable = max(0, max_total_borrowable - cumulative_borrowed)
    return additional_borrowable


# Parameters
token = 'DOGE'
initial_funds = 10000  # Initial own funds (USDT)
leverage = 3          # Leverage multiplier
initial_price = 0.2  # Initial price of DOGE (USDT)
price_increase = 0.58  # Total price increase of DOGE (58%)
price_step = 0.01     # Price increase step of DOGE (1%)

# Calculate liquidation price
result = backtest(initial_funds, leverage, initial_price, price_increase, price_step)

# Print results
print()
print(f"{leverage}x margin leverage mode, assuming current {token} price {initial_price}, buy with each {price_step * 100}% increase")
print(f"DOGE increases {price_increase * 100}% to {result['final_price']:.4f}:")
print(f"  Principal: {initial_funds} USDT")
print(f"  Holding {token} quantity: {result['doge_quantity']:.4f}")
print(f"  Cumulative borrowed: {result['cumulative_borrowed']:.2f} USDT")
print()
print(f"  ===== Profit =====")
print(f"  Total asset value: {result['doge_quantity'] * result['final_price']:.2f} USDT, Profit: {(((result['doge_quantity'] * result['final_price'] - result['cumulative_borrowed']) / initial_funds - 1) * 100):.2f}%")
print()
print(f"  ===== Liquidation =====")
print(f"  Liquidation price: {result['liquidation_price']:.4f} USDT")
print(f"  Drawdown: {((result['liquidation_price']/result['final_price'] - 1) * 100):.2f}%, compared to initial price: {((result['liquidation_price']/initial_price - 1) * 100):.2f}%")
print(f"  Remaining principal: {result['remaining_principal']:.2f}")
