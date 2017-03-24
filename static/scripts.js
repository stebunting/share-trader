function getValue(id) {
    return parseFloat($('#' + id).text().replace('£', '').replace(',', ''))
}

function gbp(value) {
    return value.toLocaleString('en-GB', {style: 'currency', currency: 'GBP'})
}

function percent(value) {
    return parseFloat(value.toFixed(1)) + '%'
}

function updateCellColours(ident) {
    var target = $(ident + 'target-edit').val();
    var stoploss = $(ident + 'stoploss-edit').val();
    var percentage = parseFloat($(ident + 'percentage').text());
    var bid = $(ident + 'bid').text();
    
    if (bid <= stoploss) {
        $(ident + 'stoploss').addClass('danger');
    } else {
        $(ident + 'stoploss').removeClass('danger');
    };
    
    if (bid >= target) {
        $(ident + 'target').addClass('success');
    } else {
        $(ident + 'target').removeClass('success');
    };
    
    if (percentage >= 20) {
        $(ident + 'percentage').addClass('success');
        $(ident + 'profitloss').addClass('success');
    } else {
        $(ident + 'percentage').removeClass('success');
        $(ident + 'profitloss').removeClass('success');
    };
    
    if (percentage < 0) {
        $(ident + 'percentage').addClass('danger');
        $(ident + 'profitloss').addClass('danger');
    } else {
        $(ident + 'percentage').removeClass('danger');
        $(ident + 'profitloss').removeClass('danger');
    };
}

// Get bid price and update cell in table
function updateBid(company) {
    var value = company['bid'] * company['quantity'] * 0.01
    var costs = company['buytradecost'] + company['selltradecost'] + company['stampduty']
    var profitloss = value - (company['buyprice'] * company['quantity'] * 0.01) - costs
    var percentage = ((10000 * (value - costs) / (company['buyprice'] * company['quantity'])) - 100)
    // Update row
    var ident = '#' + company['id'] + '-' + company['epic'] + '-'
    $(ident + 'bid').text(company['bid'].toFixed(2))
    $(ident + 'value').text(gbp(value))
    $(ident + 'profitloss').text(gbp(profitloss))
    $(ident + 'percentage').text(percent(percentage))
    
    var change = value - (company['sellprice'] * company['quantity'] * 0.01)
    
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
    
    updateCellColours(ident)
    
    data = {
        'id': company['id'],
        'bid': company['bid'],
        'value': value,
        'profitloss': profitloss,
        'percentage': percentage
    }
    return data;
}

// Get updated share price data
function refreshPrices() {
    var $btn = $('#refreshPrices').button('loading');
    $.getJSON('/updatesharedata', function(data) {
        returnData = []
        $.each(data, function(key, val) {
            returnData.push(updateBid(val));
        });
    }).done(function() {
        // Send updated data back to application to store to database
        var xhr = new XMLHttpRequest();
        xhr.open('post', '/updatedb', true);
        xhr.setRequestHeader('Content-Type', 'application/json; charset=UTF-8');
        xhr.send(JSON.stringify(returnData));
    
        // When done, set refresh button active
        $btn.button('reset');
    
        // Update last updated time
        lastUpdate = new Date();
        $('#lastupdated').text(lastUpdate.format('ddd dd mmm @ hh:MM:sstt'));
    });
    
}

$(function() {
    // Index Page
    // Sends updated data for storing when target/stop loss edited directly from table
    $('.indexform').keydown(function(e){
        if(e.keyCode == 13){
            var ident = $(this).attr('id')
            var xhr = new XMLHttpRequest();
            xhr.open('post', '/updateindex', true);
            xhr.setRequestHeader('Content-Type', 'application/json; charset=UTF-8');
            xhr.send(JSON.stringify([ident, $(this).val()]));
            
            var data = ident.split('-');
            updateCellColours('#' + data[0] + '-' + data[1] + '-');
            $(this).blur();
        }
    })
    
    // Share Page
    // Implement 2 datepickers on buydate and selldate
    var $datepickers = [$('#buydate'), $('#selldate')];
    $datepickers.forEach(function($entry) {
        //$('#anim').on('change', function() {
        //    $entry.datetimepicker('option', 'showAnim', 'slideDown');
        //});
        $entry.datetimepicker({
            setDate: $entry.attr('value'),
            dateFormat: 'yy-mm-dd',
            timeFormat: 'HH:mm:ss',
            beforeShow: function() {
                setTimeout(function(){
                    $('.ui-datepicker').css('z-index', 99999999999999);
                }, 0);
            }
        });
    });
    
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
    
    // Shares Page
    // Updates company and ADVFN link when EPIC changed
    $('#epic').keyup(function() {
        $.getJSON('/company?epic=' + $('#epic').val(), function(data) {
            if (data != '') {
                $('#company').text(data[0]['company']);
                $('#company').attr('value', data[0]['company']);
                $('.advfn-logo').remove();
                if ($('#company').parent().is('#advfndiv')) {
                    $('#company').unwrap();
                }
                $('#company').wrap('<div class="input-group" id="advfndiv">');
                $('#advfndiv').append('<span class="input-group-addon advfn-logo"><a href="http://uk.advfn.com/p.php?pid=financials&symbol=LSE:' + $('#epic').val().toUpperCase() + '" target="_blank"><img src="/static/images/advfn-logo.png" /></a></span>')
            } else {
                $('#company').text('');
                $('#company').attr('value', '');
                $('.advfn-logo').remove();
                if ($('#company').parent().is('#advfndiv')) {
                    $('#company').unwrap();
                }
            }
        });
    });
});