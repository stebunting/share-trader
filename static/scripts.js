function getValue(id) {
    return parseFloat($('#' + id).text().replace('£', '').replace(',', ''))
}

function gbp(value) {
    return value.toLocaleString('en-GB', {style: 'currency', currency: 'GBP'})
}

function percent(value) {
    return parseFloat(value.toFixed(1)) + '%'
}

// Get bid price and update cell in table
function updateBid(val) {
    var xmlHttp = new XMLHttpRequest();
    xmlHttp.onreadystatechange = function() {
        if (xmlHttp.readyState == 4 && xmlHttp.status == 200) {
            var bid = xmlHttp.responseText.replace(',', '')
            var value = bid * val['quantity'] * 0.01
            var costs = val['buytradecost'] + val['selltradecost'] + val['stampduty']
            var profitloss = value - (val['buyprice'] * val['quantity'] * 0.01) - costs
            var percentage = ((10000 * (value - costs) / (val['buyprice'] * val['quantity'])) - 100)
            
            // Update row
            var identifier = '#' + val['id'] + '-' + val['epic'] + '-'
            $(identifier + 'lookup').text(bid)
            $(identifier + 'value').text(gbp(value))
            $(identifier + 'profitloss').text(gbp(profitloss))
            $(identifier + 'percentage').text(percent(percentage))
            
            var change = value - (val['sellprice'] * val['quantity'] * 0.01)
            
            // Calculate market exposure
            var exposure = getValue('exposure') + change
            $('#exposure').text(gbp(exposure))
            
            // Calculate current sale value
            var salevalue = getValue('salevalue') + change
            $('#salevalue').text(gbp(salevalue))
            
            // Calculate profit/loss
            var totalprofitloss = getValue('profitloss') + change
            $('#profitloss').text(gbp(totalprofitloss))
            
            // Calculate percentage
            totalpercentage = 100 * ((salevalue + getValue('cash')) / getValue('capital')) - 100
            $('#percentage').text(percent(totalpercentage))
            
            // Update last updated time
            var now = new Date().toLocaleString()
            $('#lastupdated').text(now)
            
            data = {
                'id': val['id'],
                'bid': bid,
                'value': value,
                'profitloss': profitloss,
                'percentage': percentage
            }
            
            // Send updated data back to application to store to database
            var xhr = new XMLHttpRequest();
            xhr.open('post', '/update', true);
            xhr.setRequestHeader('Content-Type', 'application/json; charset=UTF-8');
            xhr.send(JSON.stringify(data));
        };
    };
    xmlHttp.open("GET", '/bid?epic=' + val['epic'], true);
    xmlHttp.send();
}

// Get symbols required to update bid prices
function refreshPrices() {
    $.getJSON('/symbols', function(data) {
        $.each(data, function(key, val) {
            updateBid(val);
        });
    });
}

$(function() {
    $('.datepicker').datepicker();
    $('#anim').on('change', function() {
        $('.datepicker').datepicker('option', 'showAnim', 'slideDown');
    });
    $('.datepicker').datepicker('option', 'dateFormat', 'yy-mm-dd');
    
    $('#stampdutycalculate').click(function() {
        var stampduty = 0;
        if (parseFloat($('#buyprice').val()) > 0 && parseInt($('#quantity').val()) > 0) {
            stampduty = parseInt($('#buyprice').val()) * parseInt($('#quantity').val()) * 0.00005;
        }
        $('#stampduty').focus().val(stampduty.toFixed(2));
    });
    
    $('#buycostcalculate').click(function() {
        var buycost = 0;
        if (parseFloat($('#buyprice').val()) > 0 && parseInt($('#quantity').val()) > 0) {
            buycost += parseFloat($('#buyprice').val()) * 0.01 * parseInt($('#quantity').val());
        }
        if (parseFloat($('#stampduty').val()) > 0) {
            buycost += parseFloat($('#stampduty').val());
        }
        if (parseFloat($('#buytradecost').val()) > 0) {
            buycost += parseFloat($('#buytradecost').val());
        }
        if (buycost < 0) {
            buycost = 0;
        }
        $('#buycost').focus().val(buycost.toFixed(2));
    });
    
    $('#sellpricecalculate').click(function() {
        var sellprice = 0;
        if (parseFloat($('#sellprice').val()) > 0 && parseInt($('#quantity').val()) > 0) {
            sellprice += parseFloat($('#sellprice').val()) * 0.01 * parseInt($('#quantity').val());
        }
        if (parseFloat($('#selltradecost').val()) > 0) {
            sellprice -= parseFloat($('#selltradecost').val());
        }
        $('#totalsale').focus().val(sellprice.toFixed(2));
    });
    
    $('#targetcalculate').click(function() {
        var targetprice = 0;
        if (parseFloat($('#buyprice').val()) > 0) {
            targetprice = parseFloat($('#buyprice').val()) * 1.2;
        }
        $('#target').focus().val(targetprice.toFixed(2));
    });
    
    $('#stoplosscalculate').click(function() {
        var stoploss = 0;
        if (parseFloat($('#buyprice').val()) > 0) {
            targetprice = parseFloat($('#buyprice').val()) * 0.9;
        }
        $('#stoploss').focus().val(targetprice.toFixed(2));
    });
    
    $('#epic').keyup(function() {
        $.getJSON('/company?epic=' + $('#epic').val(), function(data) {
            if (data != '') {
                $('#company').text(data[0]['company']);
                $('#market').text(data[0]['market']);
                $('#sector').text(data[0]['sector']);
                $('#subsector').text(data[0]['subsector']);
            } else {
                $('#company').text('');
                $('#market').text('');
                $('#sector').text('');
                $('#subsector').text('');
            }
        });
    });
});