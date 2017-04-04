// Get value from index page ids
function getValue(id) {
    return parseFloat($('#' + id).text().replace('£', '').replace(',', ''))
}

// Format number as currency GBP
function gbp(value) {
    return value.toLocaleString('en-GB', {style: 'currency', currency: 'GBP'})
}

// Format number as percent with +/- and 1 decimal place
function percent(value) {
    var symbol = '';
    if (value >= 0) {
        symbol = '+';
    }
    return symbol + parseFloat(value).toFixed(1) + '%'
}

// Update row colours
function updateCellColours(ident) {
    var target = $(ident + 'target-edit').val();
    var stoploss = $(ident + 'stoploss-edit').val();
    var percentage = parseFloat($(ident + 'percentage').text());
    var bid = $(ident + 'bid').text();
    
    if (bid <= parseFloat(stoploss)) {
        $(ident + 'stoploss').addClass('danger');
    } else {
        $(ident + 'stoploss').removeClass('danger');
    };
    
    if (bid >= parseFloat(target)) {
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
function updateRow(company) {

    // Update row
    var ident = '#' + company['id'] + '-' + company['epic'] + '-'
    $(ident + 'bid').text(company['sellprice'].toFixed(2))
    $(ident + 'value').text(gbp(company['value']))
    $(ident + 'profitloss').text(gbp(company['profitloss']))
    $(ident + 'percentage').text(percent(company['percentage']))
    
    // Update colours
    updateCellColours(ident)
}

// Update details (exposure, profit/loss etc.)
function updateTotals(company) {
    $('#exposure').text(gbp(company['exposure']));
    $('#salevalue').text(gbp(company['salevalue']));
    $('#profitloss').text(gbp(company['profitloss']));
    $('#percentage').text(percent(company['percentage']));
    
    if (company['dailyprofit'] > 0) {
        if ($('#dailyprofit').hasClass('loss')) {
            $('#dailyprofit').addClass('profit').removeClass('loss');
            $('#dailypercent').addClass('profit').removeClass('loss');
        };
    } else {
        if ($('#dailyprofit').hasClass('success')) {
            $('#dailyprofit').addClass('loss').removeClass('success');
            $('#dailyprofit').addClass('loss').removeClass('success');
        };
    }
    $('#dailyprofit').text(gbp(company['dailyprofit']));
    $('#dailypercent').text(percent(company['dailypercent']));
}

// Refresh onscreen data
function refreshPrices() {

    // Set 'refreshPrices' button to loading...
    var $btn = $('#refreshPrices').button('loading');
    if ($btn.hasClass('btn-danger')) {
        $btn.addClass('btn-primary').removeClass('btn-danger');
    };
    $btn.addClass('btn-primary').removeClass('btn-danger');
    
    // Get latest share price data from application
    // Send each price to updateBid function
    $.getJSON('/updateshareprices').done(function(data) {
        $.each(data[0], function(key, val) {
            updateRow(val);
        })
        updateTotals(data[1]);
        
        // When done, set refresh button active and reset log button
        $btn.button('reset');
        $('#logState').button('reset').addClass('btn-primary').removeClass('btn-success');
    
        // Update last updated time
        var lastUpdate = new Date();
        $('#lastupdated').text(lastUpdate.format('ddd dd mmm @ hh:MM:sstt'));
    }).fail(function() {
        $btn.button('fail');
        
        if (!$btn.hasClass('btn-danger')) {
            $btn.addClass('btn-danger').removeClass('btn-primary');
        };
    });   
}

// Function to print extra select on statement page
function divPicker(epic) {
    if ($('#cash_category').val() == '2') {
        var $options = '';
        $.getJSON('/getepics').done(function() {
            $.each(data, function(key, val) {
                $options += '<option value="' + val['epic'] + '"'
                if (epic == val['epic']) {
                    $options += ' selected="selected"'
                }
                $options += '>' + val['epic'] + ' (' + val['company'] + ')</option>';
            });
            
            if ($options != '') {
                $start = '<div class="form-group" id="extraselect"><div class="col-sm-9 col-sm-push-3"><select class="form-control" name="sharedividend" id="sharedividend">';
                $end = '</select></div></div>';
                $thing = $('#cashmodal > div:nth-child(3)').after($start + $options + $end);
            }
        });
    } else {
        if ($('#extraselect')) {
            $('#extraselect').remove();
        }
    }
}

$(function() {
    // Nav Bar
    // Changes portfolio when menu item selected
    $('.portfoliochange').on('click', function() {
        $.ajax({
            url: '/portfoliochange',
            type: 'POST',
            data: JSON.stringify($(this).attr('id')),
            contentType: 'application/json; charset=utf-8',
            dataType: 'json',
            async: false,
            success: function(msg) {
                if (msg == true) {
                    location.reload();
                }
            }
        });
    });
    
    // Fade out alert flashing
    setTimeout(function(){
        $('#flash').fadeOut(1000); }, 3000);
    
    // Index Page
    // Sends updated data for storing when target/stop loss edited directly from table
    $('.indexform').keydown(function(e){
        if(e.keyCode == 13){
            $element = $(this)
            var ident = $element.attr('id')
            $.ajax({
                url: '/updateindex',
                type: 'POST',
                data: JSON.stringify([ident, $element.val()]),
                contentType: 'application/json; charset=utf-8',
                dataType: 'json',
                async: false,
                success: function(val) {
                    var data = ident.split('-');
                    updateCellColours('#' + data[0] + '-' + data[1] + '-');
                    $element.val(val.toFixed(2)).blur();
                }
            });
        }
    })
    
    // Share Page
    // Updates company and ADVFN link when EPIC changed
    $('#epic').keyup(function() {
        $.getJSON('/getcompanyname?epic=' + $('#epic').val()).done(function(data) {
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
    
    // Share Page
    // Implement 2 datetimepickers on buydate and selldate
    var $datepickers = [$('#buydate'), $('#selldate')];
    $datepickers.forEach(function($entry) {
        $entry.datetimepicker({
            setDate: $entry.attr('value'),
            dateFormat: 'yy-mm-dd',
            timeFormat: 'HH:mm:ss',
            beforeShow: function() {
                setTimeout(function() {
                    $('.ui-datepicker').css('z-index', 99999999999999);
                }, 0);
            }
        });
    });
    
    // Share Page
    // Calculate target at 20% when button pressed
    $('#targetcalculate').click(function() {
        var targetprice = 0;
        if (parseFloat($('#buyprice').val()) > 0) {
            targetprice = parseFloat($('#buyprice').val()) * 1.2;
        }
        $('#target').focus().val(targetprice.toFixed(2));
    });
    
    // Share Page
    // Calculate stop loss at -10% when button pressed
    $('#stoplosscalculate').click(function() {
        var stoploss = 0;
        if (parseFloat($('#buyprice').val()) > 0) {
            targetprice = parseFloat($('#buyprice').val()) * 0.9;
        }
        $('#stoploss').focus().val(targetprice.toFixed(2));
    });
    
    // Share Page
    // Calculate Stamp Duty when button pressed
    $('#stampdutycalculate').click(function() {
        var stampduty = 0;
        if (parseFloat($('#buyprice').val()) > 0 && parseInt($('#quantity').val()) > 0) {
            stampduty = parseInt($('#buyprice').val()) * parseInt($('#quantity').val()) * 0.00005;
        }
        $('#stampduty').focus().val(stampduty.toFixed(2));
    });
    
    // Share Page
    // Calculate total buy cost when button pressed
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
    
    // Share Page
    // Calculate total sell cost when button pressed
    $('#sellpricecalculate').click(function() {
        var sellprice = 0;
        if (parseFloat($('#sellprice').val()) > 0 && parseInt($('#quantity').val()) > 0) {
            sellprice += parseFloat($('#sellprice').val()) * 0.01 * parseInt($('#quantity').val());
        }
        if (parseFloat($('#selltradecost').val()) > 0) {
            sellprice += parseFloat($('#selltradecost').val());
        }
        $('#value').focus().val(sellprice.toFixed(2));
    });
    
    // Statement Page
    // Implement datepicker
    $('#cashdatepicker').datepicker({
        dateFormat: 'yy-mm-dd'
    });
    
    // Statement Page
    $('#cash_category').on('change', divPicker);
    if ($('#cash_category').val() == 2) {
        $('#newCash').modal('show');
        divPicker($('#cash_category').attr('data-epic'));
    }
    console.log();
    if ($('#alertmsg').text() != '') {
        $('#newCash').modal('show');
    }
    
    // Charts Page
    // Implement 2 datetimepickers on startdate and enddate
    var $datepickers = [$('#startdate'), $('#enddate')];
    $datepickers.forEach(function($entry) {
        $entry.datepicker({
            setDate: $entry.attr('value'),
            dateFormat: 'yy-mm-dd',
            beforeShow: function() {
                setTimeout(function() {
                    $('.ui-datepicker').css('z-index', 99999999999999);
                }, 0);
            }
        });
    });
});